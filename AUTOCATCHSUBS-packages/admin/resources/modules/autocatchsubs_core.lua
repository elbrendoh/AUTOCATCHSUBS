-- AUTOCATCHSUBS: isolate globals from the original AutoSubs module.
setfenv(1, setmetatable({}, {__index = _G}))
---These are global variables given to us by the Resolve embedded LuaJIT environment
---I disable the undefined global warnings for them to stop my editor from complaining
---@diagnostic disable: undefined-global, deprecated
local ffi = ffi or require('ffi')

-- resolve is provided implicitly by the Resolve environment - no need to call Resolve() unless running in terminal
local resolve = rawget(_G, "resolve")
if resolve == nil and type(rawget(_G, "Resolve")) == "function" then
    resolve = Resolve()
end

local DEV_MODE = false

-- Server Port
local PORT = 56104

-- Windows FFI bindings for wide-character file operations to handle special characters in paths
if ffi.os == "Windows" then
    ffi.cdef [[
        typedef wchar_t WCHAR;

        int MultiByteToWideChar(
            unsigned int CodePage,
            unsigned long dwFlags,
            const char* lpMultiByteStr,
            int cbMultiByte,
            WCHAR* lpWideCharStr,
            int cchWideChar);

        void* _wfopen(const WCHAR* filename, const WCHAR* mode);
        size_t fread(void* buffer, size_t size, size_t count, void* stream);
        int fclose(void* stream);
    ]]
end

-- Helper to convert a UTF-8 string to a wide-character (WCHAR) string
local function to_wide_string(str)
    local len = #str + 1 -- Include null terminator
    local buffer = ffi.new("WCHAR[?]", len)
    local bytes_written = ffi.C.MultiByteToWideChar(65001, 0, str, -1, buffer, len)
    if bytes_written == 0 then
        error("Failed to convert string to wide string: " .. str)
    end
    return buffer
end

-- Function to read the content of a file using _wfopen on Windows for special character support
local function read_file(file_path)
    if (ffi.os == "Windows") then
        local wide_path = to_wide_string(file_path)
        local mode = to_wide_string("rb")
        local f = ffi.C._wfopen(wide_path, mode)
        if f == nil then
            error("Failed to open file: " .. file_path)
        end

        local buffer = {}
        local temp_buffer = ffi.new("char[4096]") -- 4KB buffer for reading
        while true do
            local read_bytes = ffi.C.fread(temp_buffer, 1, 4096, f)
            if read_bytes == 0 then
                break
            end
            buffer[#buffer + 1] = ffi.string(temp_buffer, read_bytes)
        end
        ffi.C.fclose(f)

        return table.concat(buffer)
    else
        local file = assert(io.open(file_path, "r"))
        local content = file:read("*a")
        file:close()
        return content
    end
end

-- Load external libraries
local socket = nil
local json = nil
local luaresolve = nil
local font_fallback = nil

-- OS SPECIFIC CONFIGURATION
local assets_path
local resources_path
local main_app
local command_open

-- Load Resolve objects
local projectManager = resolve:GetProjectManager()
local project = projectManager:GetCurrentProject()
local mediaPool = project and project:GetMediaPool()

local ANIMATED_CAPTION = "AutoSubs Caption"
local defaultTemplateImportAttempted = false

local STYLE_INDEX = {
    Fill = 1,
    Outline = 2,
    Shadow = 3,
    Background = 4
}

-- Global state for an active caption-preset edit session.
-- Populated by StartPresetEdit, consumed/cleared by CapturePresetSettings or
-- CancelPresetEdit. Holds just enough Resolve handles to tear down the
-- temporary clip/track and read the tool's input values.
local presetEditSession = nil

-- Global state for export operations
local currentExportJob = {
    active = false,
    pid = nil,
    progress = 0,
    cancelled = false,
    startTime = nil,
    audioInfo = {
        path = "",
        markIn = 0,  -- mark in (frames) - may display in UI as timecode
        markOut = 0, -- mark out (frames) - may display in UI as timecode
        offset = 0   -- offset on timeline in seconds (regardless of timeline start)
    },
    trackStates = nil,
    clipBoundaries = nil
}

-- UTF-8 aware character count
local function utf8len(s)
    local _, count = s:gsub("[^\128-\191]", "")
    return count
end

-- Helper that wraps a Resolve-facing operation in pcall and returns a
-- structured `{ error = <short reason>, detail = <underlying error> }` on
-- failure, or the function's result on success. Used so the frontend error
-- dialog can surface the actual error from Resolve instead of a generic
-- "something went wrong".
local function make_error(short, detail)
    return { error = short, detail = tostring(detail or "") }
end

-- Function to read a JSON file. Returns the decoded table on success, or
-- `nil, err` on failure so callers can surface the real reason.
local function read_json_file(file_path)
    local ok, content = pcall(read_file, file_path)
    if not ok then
        return nil, tostring(content)
    end

    -- Parse the JSON content
    local data, _, err = json.decode(content, 1, nil)
    if err then
        return nil, tostring(err)
    end
    return data
end

local function join_path(dir, filename)
    local sep = package.config:sub(1, 1) -- returns '\\' on Windows, '/' elsewhere
    -- Remove trailing separator from dir, if any
    if dir:sub(-1) == sep then
        return dir .. filename
    else
        return dir .. sep .. filename
    end
end

-- Convert hex color to RGB (Davinci Resolve uses 0-1 range)
local function hex_to_rgb(hex)
    local r, g, b = hex:match("^#?(%x%x)(%x%x)(%x%x)$")
    if r then
        return {
            Red = tonumber(r, 16) / 255,
            Green = tonumber(g, 16) / 255,
            Blue = tonumber(b, 16) / 255
        }
    else
        return nil
    end
end

-- Convert seconds to frames based on the timeline frame rate
local function to_frames(seconds, frameRate)
    return seconds * frameRate
end

-- Pause execution for a specified number of seconds (platform-independent)
local function sleep(n)
    if ffi.os == "Windows" then
        ffi.C.Sleep(n * 1000)
    else
        local ts = ffi.new("struct timespec")
        ts.tv_sec = math.floor(n)
        ts.tv_nsec = (n - math.floor(n)) * 1e9
        ffi.C.nanosleep(ts, nil)
    end
end

local function create_response(body)
    local header = "HTTP/1.1 200 OK\r\n" .. "Server: ljsocket/0.1\r\n" .. "Content-Type: application/json\r\n" ..
        "Content-Length: " .. #body .. "\r\n" .. "Connection: close\r\n" .. "\r\n"

    local response = header .. body
    return response
end

-- input of time in seconds
function JumpToTime(seconds)
    local timeline = project:GetCurrentTimeline()
    local frameRate = timeline:GetSetting("timelineFrameRate")
    local frames = to_frames(seconds, frameRate) + timeline:GetStartFrame() + 1
    local timecode = luaresolve:timecode_from_frame_auto(frames, frameRate)
    timeline:SetCurrentTimecode(timecode)
end

-- List of title strings to search for
local titleStrings = {
    "Título – Fusion", -- Spanish
    "Título Fusion", -- Portuguese
    "Generator", -- English (older versions)
    "Fusion Title", -- English
    "Titre Fusion", -- French
    "Титры на стр. Fusion", -- Russian
    "Fusion Titel", -- German
    "Titolo Fusion", -- Italian
    "Fusionタイトル", -- Japanese
    "Fusion标题", -- Chinese
    "퓨전 타이틀", -- Korean
    "Tiêu đề Fusion", -- Vietnamese
    "Fusion Titles" -- Thai
}

-- Helper function to check if a string is in the titleStrings list
-- Build quick lookup set for titleStrings for O(1) membership checks
local titleSet = {}
for _, t in ipairs(titleStrings) do
    titleSet[t] = true
end

local function is_matching_title(title)
    return titleSet[title] == true
end

local function walk_media_pool(folder, onClip)
    if not folder then return end
    local queue, seen, count, index = {folder}, {}, 0, 1
    local deadline = os.time() + 5
    while index <= #queue and index <= 512 and os.time() <= deadline do
        local current = queue[index]
        index = index + 1
        local ok, uid = pcall(function() return current:GetUniqueId() end)
        local key = ok and uid ~= nil and uid or tostring(current)
        if not seen[key] then
            seen[key] = true
            local good, clips = pcall(function() return current:GetClipList() end)
            if good then
                for _, clip in ipairs(clips or {}) do
                    count = count + 1
                    if onClip(clip) then return true end
                    if count >= 50000 or os.time() > deadline then return end
                end
            end
            local good, children = pcall(function() return current:GetSubFolderList() end)
            if good then
                for _, child in ipairs(children or {}) do
                    if #queue < 512 then queue[#queue + 1] = child end
                end
            end
        end
    end
end

local get_templates
local get_template_item
local get_video_tracks
local get_audio_tracks

-- Get a list of all Text+ templates in the media pool
-- Cooperative scan: small batches inside Resolve, background requests outside it.
-- The controller supplies a durable cache even if one Resolve API call stalls.
local templateScan = nil
function ResetTemplateScan()
    templateScan = nil
    return {reset=true}
end
local function project_key()
    project = projectManager:GetCurrentProject()
    mediaPool = project and project:GetMediaPool()
    if not project or not mediaPool then return "no-project" end
    local ok, uid = pcall(function() return project:GetUniqueId() end)
    return ok and uid or project:GetName()
end

get_templates = function()
    local key = project_key()
    if not templateScan or templateScan.key ~= key then
        templateScan = {key = key, results = setmetatable({}, {__jsontype="array"}), names = {},
            bins = {}, binIds = {}, complete = false, count = 0, total = 0, phase = "counting"}
        defaultTemplateImportAttempted = false
        templateScan.worker = coroutine.create(function()
            if not mediaPool then return end
            local queue, seen, index = {mediaPool:GetRootFolder()}, {}, 1
            local function scan()
                local batches = {}
                templateScan.count, templateScan.total, templateScan.phase = 0, 0, "counting"
                while index <= #queue and index <= 512 do
                    local folder = queue[index]
                    index = index + 1
                    local ok, uid = pcall(function() return folder:GetUniqueId() end)
                    local ident = ok and uid ~= nil and uid or tostring(folder)
                    if not seen[ident] then
                        seen[ident] = true
                        local okc, clips = pcall(function() return folder:GetClipList() end)
                        coroutine.yield()
                        if okc then
                            clips = clips or {}
                            templateScan.total = templateScan.total + #clips
                            batches[#batches+1] = {folder=folder, ident=ident, clips=clips}
                        end
                        local oks, children = pcall(function() return folder:GetSubFolderList() end)
                        if oks then
                            for _, child in ipairs(children or {}) do
                                if #queue < 512 then queue[#queue+1] = child end
                            end
                        end
                        coroutine.yield()
                    end
                end
                templateScan.phase = "scanning"
                for _, batch in ipairs(batches) do
                    local folder, ident = batch.folder, batch.ident
                            for _, clip in ipairs(batch.clips) do
                                templateScan.count = templateScan.count + 1
                                local okp, kind = pcall(function() return clip:GetClipProperty("Type") end)
                                if okp and type(kind) == "table" then kind = kind.Type end
                                if okp and is_matching_title(kind) then
                                    if not templateScan.binIds[ident] then
                                        templateScan.binIds[ident] = true
                                        templateScan.bins[#templateScan.bins+1] = folder
                                    end
                                    local okn, name = pcall(function() return clip:GetClipProperty("Clip Name") end)
                                    if okn and type(name) == "table" then name = name["Clip Name"] end
                                    if okn and type(name) == "string" and not templateScan.names[name] then
                                        templateScan.names[name] = clip
                                        local oku, uid = pcall(function() return clip:GetUniqueId() end)
                                        table.insert(templateScan.results, {label = name, value = name,
                                            mediaId = oku and uid or nil})
                                    end
                                end
                                if templateScan.count >= 50000 and templateScan.total > 50000 then
                                    error("El catÃ¡logo supera el lÃ­mite de 50000 clips")
                                end
                                coroutine.yield()
                            end
                end
            end
            scan()
            if not templateScan.names[ANIMATED_CAPTION] and not defaultTemplateImportAttempted then
                templateScan.phase = "importing"
                defaultTemplateImportAttempted = true
                local imported, result = pcall(function()
                    return mediaPool:ImportFolderFromFile(join_path(assets_path, "caption-bin.drb"))
                end)
                if imported and result then
                    -- Rescan to confirm the import; never invent a missing template.
                    queue, seen, index = {mediaPool:GetRootFolder()}, {}, 1
                    scan()
                end
            end
            table.sort(templateScan.results, function(a,b) return a.label:lower() < b.label:lower() end)
            templateScan.phase = "verifying"
        end)
    end
    if not templateScan.complete then
        local started = ffi.C.GetTickCount64()
        for _ = 1, 64 do
            local ok, err = coroutine.resume(templateScan.worker)
            if not ok then
                print("[AUTOCATCHSUBS_ERROR] Escaneo de plantillas: " .. tostring(err))
                templateScan.complete = true
                templateScan.error = tostring(err)
                break
            end
            if coroutine.status(templateScan.worker) == "dead" then
                templateScan.complete = true
                break
            end
            if tonumber(ffi.C.GetTickCount64() - started) > 40 then break end
        end
    end
    return templateScan.results
end

-- Export metadata only. No timeline insertion, selection change or project edit.
-- Fixed path inside this duplicate: the caller cannot select an arbitrary path.
function ExportTemplateCatalog()
    local key = project_key()
    if not mediaPool then return {error=true, message="No hay proyecto abierto"} end
    local root = main_app:gsub("[\\/]AUTOCATCHSUBS%.exe$", "")
    -- Resolve does NOT recursively export the root Media Pool. Export exactly
    -- those real bins where candidate titles were found, once per scan.
    local files = setmetatable({}, {__jsontype="array"})
    for index, folder in ipairs(templateScan and templateScan.bins or {}) do
        local name = string.format("textplus-bin-%03d.drb", index)
        local file = join_path(root, "state/" .. name)
        local ok, result = pcall(function() return folder:Export(file) end)
        if not ok or not result then
            return {error=true, message="No se pudo verificar un bin de tÃ­tulos", detail=tostring(result)}
        end
        files[#files+1] = name
    end
    return {exported=true, projectKey=key, files=files}
end

function GetTemplateScanStatus()
    return {complete = templateScan and templateScan.complete or false,
            projectKey = templateScan and templateScan.key or "",
            count = templateScan and templateScan.count or 0,
            total = templateScan and templateScan.total or 0,
            phase = templateScan and templateScan.phase or "counting",
            error = templateScan and templateScan.error}
end

-- Find the template item with the specified name using media pool traversal
get_template_item = function(folder, templateName)
    if templateScan and templateScan.names[templateName] then return templateScan.names[templateName] end
    local found = nil
    walk_media_pool(folder, function(clip)
        local props = clip:GetClipProperty()
        if props["Clip Name"] == templateName then
            found = clip
            return true -- early stop traversal
        end
    end)
    return found
end

function GetTimelineInfo()
    -- Get project and media pool
    project = projectManager:GetCurrentProject()
    mediaPool = project and project:GetMediaPool()

    -- Get timeline info
    local timelineInfo = {}
    local success, err = pcall(function()
        local timeline = project:GetCurrentTimeline()
        timelineInfo = {
            name = timeline:GetName(),
            timelineId = timeline:GetUniqueId(),
            timelineStart = timeline:GetStartFrame() / timeline:GetSetting("timelineFrameRate"),
            projectName = project:GetName(),
        }
    end)
    if not success then
        print("Error retrieving timeline info:", err)
        timelineInfo = {
            timelineId = "",
            name = "No timeline selected"
        }
    else
        timelineInfo["outputTracks"] = get_video_tracks()
        timelineInfo["inputTracks"] = get_audio_tracks()
    end
    return timelineInfo
end

function GetTemplates()
    return get_templates()
end

-- Get a list of possible output tracks for subtitles
get_video_tracks = function()
    local tracks = {}
    local createNewTrack = {
        value = "0",
        label = "Add to New Track"
    }
    table.insert(tracks, createNewTrack)

    local success, err = pcall(function()
        local timeline = project:GetCurrentTimeline()
        local trackCount = timeline:GetTrackCount("video")
        for i = 1, trackCount do
            local track = {
                value = tostring(i),
                label = timeline:GetTrackName("video", i)
            }
            table.insert(tracks, track)
        end
    end)
    return tracks
end

get_audio_tracks = function()
    local tracks = {}
    local success, err = pcall(function()
        local timeline = project:GetCurrentTimeline()
        local trackCount = timeline:GetTrackCount("audio")
        for i = 1, trackCount do
            local track = {
                value = tostring(i),
                label = timeline:GetTrackName("audio", i)
            }
            table.insert(tracks, track)
        end
    end)
    return tracks
end

local function reset_tracks()
    resolve:OpenPage("edit")
    local timeline = project:GetCurrentTimeline()
    local audioTracks = timeline:GetTrackCount("audio")
    for i = 1, audioTracks do
        timeline:SetTrackEnable("audio", i, currentExportJob["trackStates"][i])
    end
    currentExportJob["clipBoundaries"] = nil
end

local function check_track_empty(trackIndex, markIn, markOut)
    trackIndex = tonumber(trackIndex)
    local timeline = project:GetCurrentTimeline()
    local trackItems = timeline:GetItemListInTrack("video", trackIndex)
    for i, item in ipairs(trackItems) do
        local itemStart = item:GetStart()
        local itemEnd = item:GetEnd()
        if (itemStart <= markIn and itemEnd >= markIn) or (itemStart <= markOut and itemEnd >= markOut) then
            return false
        end
        if itemStart > markOut then
            break
        end
    end
    return #trackItems == 0
end

-- Get the current export progress
function GetExportProgress()
    if not currentExportJob.active then
        return {
            active = false,
            progress = 0,
            message = "No export in progress"
        }
    end

    if currentExportJob.cancelled then
        return {
            active = false,
            progress = currentExportJob.progress,
            cancelled = true,
            message = "Export was cancelled"
        }
    end

    -- Check if render is still in progress
    if currentExportJob.pid then
        local renderInProgress = false
        local success, result = pcall(function()
            return project:IsRenderingInProgress()
        end)

        if success then
            renderInProgress = result
        end

        if renderInProgress then
            -- Progress check using playhead position compared to 'mark in' and 'mark out' points (better than job status)
            local timeline = project:GetCurrentTimeline()
            local currentTimecode = timeline:GetCurrentTimecode()
            local frameRate = timeline:GetSetting("timelineFrameRate")

            -- Playhead position in frames
            local playheadPosition = luaresolve:frame_from_timecode(currentTimecode, frameRate)

            -- Get mark in and out from audioInfo (already in frames)
            local markIn = currentExportJob.audioInfo.markIn
            local markOut = currentExportJob.audioInfo.markOut

            -- Calculate progress percentage
            currentExportJob.progress = math.floor(((playheadPosition - markIn) / (markOut - markIn)) * 100 + 0.5)

            return {
                active = true,
                progress = currentExportJob.progress,
                message = "Export in progress...",
                pid = currentExportJob.pid
            }
        else
            -- Export completed - check if it was cancelled or completed normally
            currentExportJob.active = false

            -- Reset track states and open edit page
            reset_tracks()

            if currentExportJob.cancelled then
                return {
                    active = false,
                    progress = currentExportJob.progress,
                    cancelled = true,
                    message = "Export was cancelled"
                }
            else
                -- Normal completion
                currentExportJob.progress = 100
                return {
                    active = false,
                    progress = 100,
                    completed = true,
                    message = "Export completed successfully",
                    audioInfo = currentExportJob.audioInfo
                }
            end
        end
    else
        -- No PID available - something went wrong
        currentExportJob.active = false
        return {
            active = false,
            progress = 0,
            error = true,
            message = "Export job lost - no process ID available"
        }
    end
end

-- Cancel the current export operation
function CancelExport()
    if not currentExportJob.active then
        return {
            success = false,
            message = "No export in progress to cancel"
        }
    end

    if currentExportJob.pid then
        local success, err = pcall(function()
            project:StopRendering()
        end)

        -- reset tracks to original state and return to edit page
        reset_tracks()

        if success then
            currentExportJob.cancelled = true
            currentExportJob.active = false
            return {
                success = true,
                message = "Export cancelled successfully"
            }
        else
            return {
                success = false,
                message = "Failed to cancel export: " .. (err or "unknown error")
            }
        end
    else
        return {
            success = false,
            message = "No render job to cancel"
        }
    end
end

-- Helper function to get individual clips with their boundaries (for segment-based transcription)
-- Returns a sorted array of clip segments: { { start, end, name }, ... }
local function get_individual_clips(timeline, selectedTracks, rangeStart, rangeEnd)
    local allClips = {}
    local timelineStart = timeline:GetStartFrame()
    local frameRate = timeline:GetSetting("timelineFrameRate")

    for trackIndex, _ in pairs(selectedTracks) do
        local clips = timeline:GetItemListInTrack("audio", trackIndex)
        if clips then
            for _, clip in ipairs(clips) do
                local clipStart = clip:GetStart()
                local clipEnd = clip:GetEnd()
                local clipName = clip:GetName() or "Unnamed"

                -- Skip clips entirely outside the marker region; clamp those that overlap
                if clipEnd > rangeStart and clipStart < rangeEnd then
                    local cs = math.max(clipStart, rangeStart)
                    local ce = math.min(clipEnd, rangeEnd)

                    table.insert(allClips, {
                        startFrame = cs,
                        endFrame = ce,
                        -- Convert to seconds relative to timeline start
                        start = (cs - timelineStart) / frameRate,
                        ["end"] = (ce - timelineStart) / frameRate,
                        name = clipName
                    })
                end
            end
        end
    end

    -- Sort by start time
    table.sort(allClips, function(a, b) return a.startFrame < b.startFrame end)

    -- Merge overlapping clips (in case clips from different tracks overlap)
    local mergedClips = {}
    for _, clip in ipairs(allClips) do
        if #mergedClips == 0 then
            table.insert(mergedClips, clip)
        else
            local lastClip = mergedClips[#mergedClips]
            -- If this clip overlaps or is adjacent to the last one, merge them
            if clip.startFrame <= lastClip.endFrame then
                lastClip.endFrame = math.max(lastClip.endFrame, clip.endFrame)
                lastClip["end"] = math.max(lastClip["end"], clip["end"])
                lastClip.name = lastClip.name .. " + " .. clip.name
            else
                table.insert(mergedClips, clip)
            end
        end
    end

    return mergedClips
end

-- Helper function to resolve in/out markers to absolute timeline frame positions.
-- timeline:GetMarkInOut() returns a dict like {audio={in=0,out=134}, video={...}}
-- where values are RELATIVE to the timeline start (0-based). Clip positions
-- (clip:GetStart()/GetEnd()) however are ABSOLUTE timeline frames, so we must
-- offset markers by timeline:GetStartFrame() before comparing.
-- If only one of in/out is set, the missing side defaults to the timeline
-- start/end frame respectively.
local function get_marker_range(timeline)
    local startFrame = timeline:GetStartFrame()
    local endFrame = timeline:GetEndFrame()

    local marks = timeline:GetMarkInOut() or {}
    -- Prefer audio markers; fall back to video if audio not present
    local m = marks["audio"] or marks["video"] or {}

    local inAbs = m["in"] and (m["in"] + startFrame) or startFrame
    local outAbs = m["out"] and (m["out"] + startFrame) or endFrame

    return inAbs, outAbs
end

-- Helper function to find clip boundaries on selected audio tracks within in/out markers.
-- Clips entirely outside the marker region are ignored. Clips that overlap the
-- region are clamped to the marker boundaries.
local function get_clip_boundaries(timeline, selectedTracks, rangeStart, rangeEnd)
    local earliestStart = nil
    local latestEnd = nil

    for trackIndex, _ in pairs(selectedTracks) do
        local clips = timeline:GetItemListInTrack("audio", trackIndex)
        if clips then
            for _, clip in ipairs(clips) do
                local clipStart = clip:GetStart()
                local clipEnd = clip:GetEnd()

                -- Skip clips completely outside the marker region
                if clipEnd > rangeStart and clipStart < rangeEnd then
                    local start = math.max(clipStart, rangeStart)
                    local end_ = math.min(clipEnd, rangeEnd)

                    if earliestStart == nil or start < earliestStart then
                        earliestStart = start
                    end
                    if latestEnd == nil or end_ > latestEnd then
                        latestEnd = end_
                    end
                end
            end
        end
    end

    return earliestStart, latestEnd
end


-- Export audio from selected tracks
-- inputTracks is a table of track indices to export
function ExportAudio(outputDir, inputTracks, exportRange)
    -- Check if another export is already in progress
    if project:IsRenderingInProgress() then
        return {
            error = true,
            message = "Another export is already in progress"
        }
    end

    -- Initialize export job state
    currentExportJob = {
        active = true,
        pid = nil,
        progress = 0,
        cancelled = false,
        startTime = os.time(),
        audioInfo = nil,
        trackStates = nil
    }

    local timeline = project:GetCurrentTimeline()
    local audioTracks = timeline:GetTrackCount("audio")

    -- Save track states immediately for restoration or error
    local trackStates = {}
    for i = 1, audioTracks do
        local state = timeline:GetIsTrackEnabled("audio", i)
        trackStates[i] = state
    end
    currentExportJob["trackStates"] = trackStates

    -- Create Set of selected track indices for quick lookup
    local selected = {}
    for _, v in ipairs(inputTracks) do
        local n = tonumber(v)
        if n then selected[n] = true end
    end

    -- Enable selected tracks (disable / mute others)
    for i = 1, audioTracks do
        local isEnabled = selected[i] == true
        timeline:SetTrackEnable("audio", i, isEnabled)
    end

    local exportName = "autosubs-exported-audio-" ..
        os.date("!%Y%m%d-%H%M%S") .. "-" .. tostring(math.random(100000, 999999))

    -- Build render settings
    local renderSettings = {
        TargetDir = outputDir,
        CustomName = exportName,
        RenderMode = "Single clip",
        IsExportVideo = false,
        IsExportAudio = true,
        AudioBitDepth = 24,
        AudioSampleRate = 44100
    }

    -- Determine the broad region to export (in/out markers or entire timeline)
    local rangeStart, rangeEnd
    if exportRange == "inout" then
        local ok, inPt, outPt = pcall(get_marker_range, timeline)
        if ok then
            rangeStart, rangeEnd = inPt, outPt
        else
            -- GetMarkInOut() requires Resolve 20+, fall back to current In/Out points
            print("[AutoSubs] No markers found — using current In/Out points")
        end
    else
        rangeStart = timeline:GetStartFrame()
        rangeEnd = timeline:GetEndFrame()
    end

    -- Trim to actual clip boundaries (skip leading/trailing silence) and apply to render
    if rangeStart then
        local exportStart, exportEnd = get_clip_boundaries(timeline, selected, rangeStart, rangeEnd)
        renderSettings.MarkIn = exportStart
        renderSettings.MarkOut = exportEnd
        print("[AutoSubs] Export range: " .. exportStart .. " - " .. exportEnd)
    end

    -- Must switch to Deliver page to start render and customise settings (wierd quirk of Resolve API)
    resolve:OpenPage("deliver")
    project:LoadRenderPreset('Audio Only')

    project:SetRenderSettings(renderSettings)

    local success, err = pcall(function()
        local pid = project:AddRenderJob()
        currentExportJob.pid = pid
        project:StartRendering(pid)

        local renderJobList = project:GetRenderJobList()
        local jobInfo = renderJobList[#renderJobList]

        -- Calculate offset to align subtitles back to timeline (exported audio starts at mark in, not timeline 0)
        local framesFromTimelineStart = jobInfo["MarkIn"] - timeline:GetStartFrame()
        local timeOffsetInSeconds = framesFromTimelineStart / timeline:GetSetting("timelineFrameRate")

        local audioInfo = {
            path = join_path(jobInfo["TargetDir"], jobInfo["OutputFilename"]),
            markIn = jobInfo["MarkIn"],
            markOut = jobInfo["MarkOut"],
            offset = timeOffsetInSeconds
        }
        currentExportJob.audioInfo = audioInfo

        print("Export started with PID: " .. pid)
    end)

    -- Handle export start result
    if not success then
        reset_tracks()
        currentExportJob.active = false
        local detail = tostring(err or "unknown error")
        print("[AutoSubs] ExportAudio failed to start: " .. detail)
        return {
            error = true,
            message = "Failed to start audio export",
            detail = detail
        }
    else
        -- Export started successfully - return immediately
        return {
            started = true,
            message = "Export started successfully. Use GetExportProgress to monitor progress.",
            pid = currentExportJob.pid
        }
    end
end

local function sanitize_track_index(timeline, trackIndex, markIn, markOut)
    -- Only create a new track if trackIndex is explicitly "0" (new track), empty/nil, or invalid
    -- Respect user's track selection regardless of whether the track is empty
    if trackIndex == "0" or trackIndex == "" or trackIndex == nil or tonumber(trackIndex) > timeline:GetTrackCount("video") then
        trackIndex = timeline:GetTrackCount("video") + 1
        timeline:AddTrack("video")
    end

    return tonumber(trackIndex)
end

local function set_speaker_styling(speaker, tool, isAnimated)
    -- Return early if no custom color set for speaker
    if not speaker.color or speaker.color == "" then return end

    local styleId = STYLE_INDEX[speaker.style]

    -- Convert hex color to rgb
    local color = hex_to_rgb(speaker.color)
    if color == nil then return end

    -- Update color for that style e.g. Fill or Outline
    for key, value in ipairs(color) do
        if isAnimated then
            tool:SetInput(speaker.style .. "Color" .. key, value)
        else
            tool:SetInput(key .. styleId, value)
        end
    end

    -- Ensure the selected style is enabled
    if isAnimated then
        tool:SetInput(speaker.style .. "Enabled", 1)
    else
        tool:SetInput("Enabled" .. styleId, 1)
    end
end

-- Check for existing clips on a track that would conflict with new subtitles
-- Returns conflict info: { hasConflicts, conflictingClips: [{start, end, name}], trackName }
function CheckTrackConflicts(filePath, trackIndex)
    local timeline = project:GetCurrentTimeline()
    if not timeline then
        return { hasConflicts = false, error = "No active timeline" }
    end
    local timelineStart = timeline:GetStartFrame()
    local frame_rate = timeline:GetSetting("timelineFrameRate")

    -- Read the subtitle data to get time ranges
    local data, readErr = read_json_file(filePath)
    if type(data) ~= "table" then
        return {
            hasConflicts = false,
            error = "Could not read subtitle file",
            detail = readErr or "unknown error"
        }
    end

    local subtitles = {}
    for _, subtitle in ipairs(data["segments"] or {}) do
        if type(subtitle.text) == "string" and subtitle.text:match("%S") then
            subtitles[#subtitles+1] = subtitle
        end
    end
    if not subtitles or #subtitles == 0 then
        return { hasConflicts = false, message = "No subtitles to add" }
    end

    -- Get the time range of new subtitles
    local firstSubStart = to_frames(subtitles[1]["start"], frame_rate) + timelineStart
    local lastSubEnd = to_frames(subtitles[#subtitles]["end"], frame_rate) + timelineStart

    -- Validate track index
    trackIndex = tonumber(trackIndex)
    if not trackIndex or trackIndex <= 0 or trackIndex > timeline:GetTrackCount("video") then
        return { hasConflicts = false, trackExists = false, message = "Track does not exist" }
    end

    -- Get track name
    local trackName = timeline:GetTrackName("video", trackIndex) or ("Video " .. trackIndex)

    -- Get existing clips on the track
    local existingClips = timeline:GetItemListInTrack("video", trackIndex)
    if not existingClips or #existingClips == 0 then
        return { hasConflicts = false, trackName = trackName, message = "Track is empty" }
    end

    -- Find clips that overlap with the new subtitle range
    local conflictingClips = {}
    for _, clip in ipairs(existingClips) do
        local clipStart = clip:GetStart()
        local clipEnd = clip:GetEnd()

        -- Check if clip overlaps with subtitle range
        if clipStart < lastSubEnd and clipEnd > firstSubStart then
            table.insert(conflictingClips, {
                start = (clipStart - timelineStart) / frame_rate,
                ["end"] = (clipEnd - timelineStart) / frame_rate,
                name = clip:GetName() or "Unnamed clip"
            })
        end
    end

    return {
        hasConflicts = #conflictingClips > 0,
        conflictingClips = conflictingClips,
        trackName = trackName,
        subtitleRange = {
            start = (firstSubStart - timelineStart) / frame_rate,
            ["end"] = (lastSubEnd - timelineStart) / frame_rate
        },
        totalConflicts = #conflictingClips
    }
end

local function load_subtitle_data(filePath)
    local data, err = read_json_file(filePath)
    if type(data) ~= "table" then
        return nil, err or "Could not parse subtitle JSON"
    end
    return data
end

local function get_mark_in_out(timeline, data)
    local timelineStart = timeline:GetStartFrame()
    local timelineEnd = timeline:GetEndFrame()
    local markIn = data["mark_in"]
    local markOut = data["mark_out"]

    if not markIn or not markOut then
        local success, err = pcall(function()
            local markInOut = timeline:GetMarkInOut()
            markIn = (markInOut.audio["in"] and markInOut.audio["in"] + timelineStart) or timelineStart
            markOut = (markInOut.audio["out"] and markInOut.audio["out"] + timelineStart) or timelineEnd
        end)

        if not success then
            markIn = timelineStart
            markOut = timelineEnd
        end
    end

    return markIn, markOut
end

local function sanitize_speaker_tracks(timeline, speakers, trackIndex, markIn, markOut)
    if not speakers or #speakers == 0 then
        return speakers
    end

    for _, speaker in ipairs(speakers) do
        if speaker.track == nil or speaker.track == "" then
            speaker.track = trackIndex
        else
            speaker.track = sanitize_track_index(timeline, speaker.track, markIn, markOut)
        end
    end

    return speakers
end

local function get_template(rootFolder, templateName)
    if templateName == "" then
        local availableTemplates = get_templates()
        if #availableTemplates > 0 then
            templateName = availableTemplates[1].value
        end
    end

    local templateItem = nil
    if templateName ~= nil and templateName ~= "" then
        templateItem = get_template_item(rootFolder, templateName)
    end
    if not templateItem then
        templateItem = get_template_item(rootFolder, "Default Template")
    end
    if not templateItem then
        return nil, nil, "Could not find subtitle template '" .. tostring(templateName) .. "' in media pool"
    end

    local template_frame_rate = templateItem:GetClipProperty()["FPS"]
    return templateItem, template_frame_rate, nil
end

local function apply_conflict_mode(timeline, subtitles, trackIndex, conflictMode, frame_rate, timelineStart)
    if conflictMode == "new_track" then
        local existingClips = timeline:GetItemListInTrack("video", trackIndex)
        if existingClips and #existingClips > 0 then
            local firstSubStart = to_frames(subtitles[1]["start"], frame_rate) + timelineStart
            local lastSubEnd = to_frames(subtitles[#subtitles]["end"], frame_rate) + timelineStart
            local hasConflict = false
            for _, clip in ipairs(existingClips) do
                if clip:GetStart() < lastSubEnd and clip:GetEnd() > firstSubStart then
                    hasConflict = true
                    break
                end
            end
            if hasConflict then
                trackIndex = timeline:GetTrackCount("video") + 1
                timeline:AddTrack("video")
                print("[AutoSubs] Created new track: " .. trackIndex)
            else
                print("[AutoSubs] No conflicts on track " .. trackIndex .. ", using existing track")
            end
        else
            print("[AutoSubs] Track " .. trackIndex .. " is empty, using existing track")
        end
        return trackIndex, subtitles, nil
    end

    if conflictMode == "replace" then
        local existingClips = timeline:GetItemListInTrack("video", trackIndex)
        if existingClips and #existingClips > 0 then
            local firstSubStart = to_frames(subtitles[1]["start"], frame_rate) + timelineStart
            local lastSubEnd = to_frames(subtitles[#subtitles]["end"], frame_rate) + timelineStart

            local clipsToDelete = {}
            for _, clip in ipairs(existingClips) do
                local clipStart = clip:GetStart()
                local clipEnd = clip:GetEnd()
                if clipStart < lastSubEnd and clipEnd > firstSubStart then
                    table.insert(clipsToDelete, clip)
                end
            end

            for _, clip in ipairs(clipsToDelete) do
                timeline:DeleteClips({ clip }, false)
            end
            print("[AutoSubs] Deleted " .. #clipsToDelete .. " conflicting clips")
        end

        return trackIndex, subtitles, nil
    end

    if conflictMode == "skip" then
        local existingClips = timeline:GetItemListInTrack("video", trackIndex)
        if existingClips and #existingClips > 0 then
            local filteredSubtitles = {}
            for _, subtitle in ipairs(subtitles) do
                local subStart = to_frames(subtitle["start"], frame_rate) + timelineStart
                local subEnd = to_frames(subtitle["end"], frame_rate) + timelineStart

                local hasConflict = false
                for _, clip in ipairs(existingClips) do
                    local clipStart = clip:GetStart()
                    local clipEnd = clip:GetEnd()
                    if subStart < clipEnd and subEnd > clipStart then
                        hasConflict = true
                        break
                    end
                end

                if not hasConflict then
                    table.insert(filteredSubtitles, subtitle)
                end
            end

            print("[AutoSubs] Skipped " .. (#subtitles - #filteredSubtitles) .. " conflicting subtitles")
            subtitles = filteredSubtitles

            if #subtitles == 0 then
                print("[AutoSubs] All subtitles skipped due to conflicts")
                return trackIndex, subtitles,
                    { success = true, message = "All subtitles skipped due to existing content", added = 0 }
            end
        end
    end

    return trackIndex, subtitles, nil
end

local function get_speaker_from_id(speakers, id)
    local speakerIndex = tonumber(id)
    if speakerIndex == nil then
        return nil
    end

    local speaker = speakers[speakerIndex]
    if speaker ~= nil then
        return speaker
    end

    return nil
end

local function build_clip_list(subtitles, speakers, speakersExist, trackIndex, templateItem, frame_rate,
                               template_frame_rate, timelineStart)
    local joinThreshold = frame_rate
    local clipList = {}
    for i, subtitle in ipairs(subtitles) do
        local start_frame = to_frames(subtitle["start"], frame_rate)
        local end_frame = to_frames(subtitle["end"], frame_rate)
        local timeline_pos = timelineStart + start_frame
        local clip_timeline_duration = end_frame - start_frame

        if i < #subtitles then
            local next_start = timelineStart + to_frames(subtitles[i + 1]["start"], frame_rate)
            local frames_between = next_start - (timeline_pos + clip_timeline_duration)
            if frames_between < joinThreshold then
                clip_timeline_duration = clip_timeline_duration + frames_between + 1
            end
        end

        local duration = (clip_timeline_duration / frame_rate) * template_frame_rate

        local itemTrack = trackIndex
        if speakersExist then
            local speaker = get_speaker_from_id(speakers, subtitle.speaker_id)
            if speaker and speaker.track ~= nil and speaker.track ~= "" then
                itemTrack = speaker.track
            end
        end

        local newClip = {
            mediaPoolItem = templateItem,
            mediaType = 1,
            startFrame = 0,
            endFrame = duration,
            recordFrame = timeline_pos,
            trackIndex = itemTrack
        }

        table.insert(clipList, newClip)
    end

    return clipList
end

local function to_word_timing(transcript_words, frameRate, segmentStart)
    local result = {}
    local startIndex = 0

    for _, word in ipairs(transcript_words) do
        local endIndex = startIndex + utf8len(word.word) - 1
        table.insert(result, {
            startIndex = startIndex,
            endIndex   = endIndex,
            startFrame = math.floor((word.start - segmentStart) * frameRate),
            endFrame   = math.floor((word["end"] - segmentStart) * frameRate),
        })
        startIndex = endIndex + 1
    end

    return result
end

-- Applies subtitle text + styling to each appended timeline item. Instead of
-- spamming one print per failed clip, we aggregate failures and return a
-- summary so the caller can surface a single clean error.
-- Returns: { failed = N, total = M, firstError = "..." }
local function apply_subtitle_text(timelineItems, subtitles, speakers, speakersExist, isAnimated, presetSettings)
    local hasPresetSettings = isAnimated and presetSettings ~= nil and next(presetSettings) ~= nil
    local failed = 0
    local noFusionComp = 0
    local firstError = nil
    for i, timelineItem in ipairs(timelineItems) do
        local success, err = pcall(function()
            local subtitle = subtitles[i]
            local subtitleText = subtitle["text"]

            local fusionCompCount = timelineItem:GetFusionCompCount()
            if not fusionCompCount then
                noFusionComp = noFusionComp + 1
                error("template clip has no Fusion composition (GetFusionCompCount returned nil) — your DaVinci Resolve version may be incompatible")
            end
            if fusionCompCount > 0 then
                local comp = timelineItem:GetFusionCompByIndex(1)
                local template = comp:FindTool("Template") or comp:FindToolByID("TextPlus")
                if isAnimated then
                    local framerate = tonumber(comp:GetPrefs("Comp.FrameFormat.Rate"))
                    local wordTiming = to_word_timing(subtitle.words, framerate, subtitle.start)
                    local autosubsTool = comp:FindTool("AutoSubs")
                    autosubsTool:SetData("WordTiming", wordTiming) -- Will be applied to keyframes when text is updated
                    template:SetInput("Text", subtitleText)        -- AutoSubs Macro uses custom text input

                    -- Apply caption preset settings via the macro's built-in helper
                    -- so inspector values captured during a preset edit are faithfully
                    -- reproduced here. Swallow errors for forward-compat with future
                    -- macro versions that may gain/lose fields.
                    if hasPresetSettings then
                        local applyOk, applyErr = pcall(function()
                            local setter = autosubsTool:GetData("SetInputValues")
                            if setter and setter ~= "" then
                                loadstring(setter)()(comp, autosubsTool, presetSettings)
                            end
                        end)
                        if not applyOk then
                            -- Re-raise so it's counted as a per-clip failure.
                            error("preset apply failed: " .. tostring(applyErr))
                        end
                    end
                else
                    template:SetInput("StyledText", subtitleText)
                end

                if speakersExist then
                    local speaker = get_speaker_from_id(speakers, subtitle.speaker_id)
                    if speaker then
                        set_speaker_styling(speaker, template, isAnimated)
                    end
                end

                timelineItem:SetClipColor("Green") -- Visualise updated clips
            end
        end)

        if not success then
            failed = failed + 1
            if firstError == nil then firstError = tostring(err) end
        end
    end

    if noFusionComp > 0 then
        print(string.format("[AutoSubs] %d of %d subtitle clips had no Fusion composition (GetFusionCompCount returned nil). This usually means your DaVinci Resolve version is incompatible with the AutoSubs Caption template.",
            noFusionComp, #timelineItems))
    end
    if failed > 0 then
        print(string.format("[AutoSubs] Failed to place %d of %d subtitles. First error: %s",
            failed, #timelineItems, tostring(firstError)))
    end

    return { failed = failed, total = #timelineItems, firstError = firstError, noFusionComp = noFusionComp }
end

-- Add subtitles to the timeline using the specified template
-- conflictMode: "replace" (delete existing), "skip" (write around conflicts), "new_track" (use new track), nil (default/old behavior)
-- presetSettings: optional opaque table of AutoSubs Caption macro input values
-- (captured via StartPresetEdit/CapturePresetSettings). Ignored for non-animated templates.
function AddSubtitles(filePath, trackIndex, templateName, conflictMode, presetSettings)
    resolve:OpenPage("edit")

    local data, loadErr = load_subtitle_data(filePath)
    if not data then
        return make_error("Failed to load subtitle file", loadErr)
    end

    ---@type { mark_in: integer, mark_out: integer, segments: table, speakers: table }
    data = data

    local timeline = project:GetCurrentTimeline()
    if not timeline then
        return make_error("Failed to add subtitles", "No active timeline in Resolve")
    end
    local timelineStart = timeline:GetStartFrame()
    local markIn, markOut = get_mark_in_out(timeline, data)
    local subtitles = {}
    for _, subtitle in ipairs(data["segments"] or {}) do
        if type(subtitle.text) == "string" and subtitle.text:match("%S") then
            subtitles[#subtitles+1] = subtitle
        end
    end
    local speakers = data["speakers"]

    if not subtitles or #subtitles == 0 then
        return make_error("Failed to add subtitles", "Transcript has no segments")
    end

    local speakersExist = false
    if speakers and #speakers > 0 then
        speakersExist = true
    end

    trackIndex = sanitize_track_index(timeline, trackIndex, markIn, markOut)

    local frame_rate = timeline:GetSetting("timelineFrameRate")

    local earlyResult = nil
    trackIndex, subtitles, earlyResult = apply_conflict_mode(timeline, subtitles, trackIndex, conflictMode, frame_rate,
        timelineStart)
    if earlyResult then
        return earlyResult
    end

    speakers = sanitize_speaker_tracks(timeline, speakers, trackIndex, markIn, markOut)

    local rootFolder = mediaPool:GetRootFolder()
    local templateItem, template_frame_rate, templateErr = get_template(rootFolder, templateName)
    if not templateItem then
        return make_error("Template not found", templateErr)
    end

    local clipList = build_clip_list(subtitles, speakers, speakersExist, trackIndex, templateItem, frame_rate,
        template_frame_rate, timelineStart)

    -- AppendToTimeline can fail (e.g. locked timeline, invalid clips). Surface
    -- the real Resolve error instead of silently returning an empty table.
    local appendOk, timelineItems = pcall(function()
        return mediaPool:AppendToTimeline(clipList)
    end)
    if not appendOk then
        return make_error("Failed to add subtitles to timeline", timelineItems)
    end
    if type(timelineItems) ~= "table" or #timelineItems == 0 then
        return make_error("Failed to add subtitles to timeline",
            "Resolve did not return any timeline items from AppendToTimeline")
    end

    local isAnimated = templateName == ANIMATED_CAPTION and true or false

    -- Auto-swap the caption Font for non-Latin transcript languages when the
    -- user is still on the macro's default font. Uses the transcript JSON's
    -- `language` field so older transcripts in a different language still get
    -- the right font even if the app's current language setting has moved on.
    local fontSwap = nil
    if isAnimated and font_fallback then
        presetSettings, fontSwap = font_fallback.maybe_override(presetSettings, data["language"])
    end

    local applyStats = apply_subtitle_text(timelineItems, subtitles, speakers, speakersExist, isAnimated,
        presetSettings)

    -- Force timeline refresh by jumping to the first subtitle
    if subtitles and #subtitles > 0 then
        JumpToTime(subtitles[1].start)
    end

    -- If some (but not all) clips failed to receive text/styling, still report
    -- success but include a warning summary so the UI can mention it.
    if applyStats and applyStats.failed > 0 and applyStats.failed < applyStats.total then
        local warning = string.format("Failed to place %d of %d subtitles", applyStats.failed, applyStats.total)
        if applyStats.noFusionComp and applyStats.noFusionComp > 0 then
            warning = warning .. string.format(" (%d had no Fusion composition — your Resolve version may be incompatible)", applyStats.noFusionComp)
        end
        return {
            ok = true,
            fontSwap = fontSwap,
            warning = warning,
            detail = applyStats.firstError
        }
    elseif applyStats and applyStats.failed == applyStats.total and applyStats.total > 0 then
        local short = string.format("Failed to place all %d subtitles", applyStats.total)
        if applyStats.noFusionComp and applyStats.noFusionComp == applyStats.total then
            short = short .. " — template clips had no Fusion composition. Check that your DaVinci Resolve version supports the AutoSubs Caption template."
        end
        return make_error(short, applyStats.firstError)
    end

    return { ok = true, fontSwap = fontSwap }
end

local function extract_frame(comp, exportDir)
    -- Lock the composition to prevent redraws and pop-ups during scripting [15, 16]
    comp:Lock()

    -- Access the Saver tool by its name (assuming it exists in the comp)
    local mySaver = comp:AddTool("Saver")

    local outputPath = ""

    if mySaver ~= nil then
        -- Set the output filename for the Saver tool [6, 7]
        -- Make sure to provide a full path and desired image format extension
        local name = mySaver.Name
        local settings = mySaver:SaveSettings()
        settings.Tools[name].Inputs.Clip.Value["Filename"] = join_path(exportDir, "subtitle-preview-0.png")
        settings.Tools[name].Inputs.Clip.Value["FormatID"] = "PNGFormat"
        settings.Tools[name].Inputs["OutputFormat"]["Value"] = "PNGFormat"
        mySaver:LoadSettings(settings)

        -- Set the input for the Saver tool to the MediaOut tool
        local mediaOut = comp:FindToolByID("MediaOut")
        mySaver:SetInput("Input", mediaOut)

        -- Get the middle frame of the clip (best representative)
        local frameIndex = math.floor(comp:GetAttrs().COMPN_GlobalEnd / 2)

        -- Trigger the render for only the specified frame through the Saver tool [1, 13, 14]
        local success = comp:Render({
            Start = frameIndex, -- Start rendering at this frame
            End = frameIndex,   -- End rendering at this frame (same in this case)
            Tool = mySaver,     -- Render up to this specific Saver tool [13]
            Wait = true         -- Wait for the render to complete before continuing the script [19]
        })

        local outputFilename = "subtitle-preview-" .. frameIndex .. ".png"
        outputPath = join_path(exportDir, outputFilename)

        if success then
            print("Frame " .. frameIndex .. " successfully saved by " .. mySaver.Name .. " to " .. outputPath)
        else
            print("Failed to save frame " .. frameIndex)
        end
    else
        print("Saver tool 'MySaver' not found in the composition.")
    end

    -- Unlock the composition after changes are complete [15, 20]
    comp:Unlock()

    return outputPath
end

-- place example subtitle on timeline with theme and export frame
-- `language` (optional): ISO code of the transcript this preview represents,
-- used for language-aware font fallback on the AutoSubs Caption macro.
function GeneratePreview(speaker, templateName, presetSettings, exportDir, language)
    local timeline = project:GetCurrentTimeline()
    if not timeline then
        return make_error("Failed to generate preview", "No active timeline in Resolve")
    end
    local rootFolder = mediaPool:GetRootFolder()

    -- Resolve the template item
    local templateItem = get_template_item(rootFolder, templateName)
    if not templateItem then
        return make_error("Failed to generate preview",
            "Could not find subtitle template '" .. tostring(templateName) .. "' in media pool")
    end

    -- Add new track and place item at start of timeline (avoids overwriting existing clips)
    local setupOk, setupErr = pcall(function()
        timeline:AddTrack("video")
    end)
    if not setupOk then
        return make_error("Failed to generate preview", setupErr)
    end

    local trackIndex = timeline:GetTrackCount("video")
    local fps = templateItem:GetClipProperty()["FPS"]

    local appendOk, appended = pcall(function()
        return mediaPool:AppendToTimeline({ {
            mediaPoolItem = templateItem,
            startFrame = 0,
            endFrame = fps * 5, -- set preview to 5 seconds long
            recordFrame = timeline:GetStartFrame(),
            trackIndex = trackIndex
        } })
    end)
    if not appendOk or type(appended) ~= "table" or not appended[1] then
        pcall(function() timeline:DeleteTrack("video", trackIndex) end)
        return make_error("Failed to generate preview",
            (not appendOk) and tostring(appended) or "AppendToTimeline returned no items")
    end
    local timelineItem = appended[1]

    local isAnimated = templateName == ANIMATED_CAPTION and true or false
    local fontSwap = nil
    if isAnimated and font_fallback then
        presetSettings, fontSwap = font_fallback.maybe_override(presetSettings, language)
    end

    local outputPath = nil
    local success, err = pcall(function()
        if timelineItem:GetFusionCompCount() > 0 then
            local comp = timelineItem:GetFusionCompByIndex(1)
            local tool = comp:FindToolByID("TextPlus")
            tool:SetInput("StyledText", "Subtitle Example Text")
            set_speaker_styling(speaker, tool)
            if fontSwap and fontSwap.to then
                pcall(function() tool:SetInput("Font", fontSwap.to) end)
            end
            outputPath = extract_frame(comp, exportDir)
        end
    end)

    -- Always clean up, even on failure, so the user isn't left with a stray track.
    pcall(function() timeline:DeleteClips({ timelineItem }) end)
    pcall(function() timeline:DeleteTrack("video", trackIndex) end)

    if not success then
        return make_error("Failed to generate preview", err)
    end
    if not outputPath or outputPath == "" then
        return make_error("Failed to generate preview",
            "Template has no Fusion composition to render from")
    end

    return { path = outputPath, fontSwap = fontSwap }
end

-- ---------------------------------------------------------------------------
-- Caption-preset editing
--
-- The AutoSubs animated caption macro exposes two helper scripts via
-- `tool:GetData("GetInputValues")` and `tool:GetData("SetInputValues")`. We
-- use these to let the user tweak preset parameters in Resolve's Fusion
-- inspector and round-trip those values back into a JSON preset we store in
-- the app.
--
-- The three endpoints below form a mini state machine driven from the app:
--   StartPresetEdit  -> drops a caption clip on a temp track, opens Fusion.
--   CapturePresetSettings -> reads tool inputs, tears down the temp track.
--   CancelPresetEdit -> tears down without reading.
-- ---------------------------------------------------------------------------

-- Remove the temp clip + track created by StartPresetEdit, if any, and return
-- to the edit page. Safe to call without an active session.
local function teardown_preset_edit_session()
    if presetEditSession == nil then return end
    local timeline = project:GetCurrentTimeline()
    pcall(function()
        if timeline and presetEditSession.timelineItem then
            timeline:DeleteClips({ presetEditSession.timelineItem })
        end
    end)
    pcall(function()
        if timeline and presetEditSession.trackIndex then
            timeline:DeleteTrack("video", presetEditSession.trackIndex)
        end
    end)
    pcall(function() resolve:OpenPage("edit") end)
    presetEditSession = nil
end

function StartPresetEdit(initialSettings)
    -- Never stack sessions. Callers are expected to finalise or cancel first.
    if presetEditSession ~= nil then
        return { error = "A preset edit is already in progress" }
    end

    local timeline = project:GetCurrentTimeline()
    if not timeline then
        return { error = "No active timeline" }
    end

    local rootFolder = mediaPool:GetRootFolder()
    local templateItem = get_template_item(rootFolder, ANIMATED_CAPTION)
    if not templateItem then
        return { error = "Could not find '" .. ANIMATED_CAPTION .. "' template in media pool" }
    end

    local ok, err = pcall(function()
        timeline:AddTrack("video")
        local trackIndex = timeline:GetTrackCount("video")
        local fps = tonumber(templateItem:GetClipProperty()["FPS"]) or 24
        local position = timeline:GetStartFrame()

        local appended = mediaPool:AppendToTimeline({ {
            mediaPoolItem = templateItem,
            startFrame = 0,
            endFrame = math.floor(fps * 5), -- 5-second preview clip
            recordFrame = position,
            trackIndex = trackIndex,
        } })
        local timelineItem = appended and appended[1]
        if not timelineItem then
            error("Failed to append preview clip to timeline")
        end

        -- Open caption in Fusion (move playhead over it and open Fusion page)
        timeline:SetCurrentTimecode(timeline:GetStartTimecode())
        local comp = timelineItem:GetFusionCompByIndex(1)
        local tool = comp:FindTool("AutoSubs")

        -- Apply any existing settings so editing an existing preset starts
        -- from its current look rather than macro defaults.
        if tool and initialSettings ~= nil and next(initialSettings) ~= nil then
            pcall(function()
                local setter = tool:GetData("SetInputValues")
                if setter and setter ~= "" then
                    loadstring(setter)()(comp, tool, initialSettings)
                end
            end)
        end

        presetEditSession = {
            trackIndex = trackIndex,
            timelineItem = timelineItem,
            comp = comp,
            tool = tool,
        }
    end)

    if not ok then
        -- Best-effort cleanup so we don't leave an orphan track.
        teardown_preset_edit_session()
        return { error = "Failed to start preset edit: " .. tostring(err) }
    end

    return { ok = true }
end

function CapturePresetSettings()
    if presetEditSession == nil then
        return { error = "No preset edit in progress" }
    end

    local tool = presetEditSession.tool
    if not tool then
        teardown_preset_edit_session()
        return { error = "AutoSubs tool not found in preview composition" }
    end

    local settings = nil
    local ok, err = pcall(function()
        local getter = tool:GetData("GetInputValues")
        if not getter or getter == "" then
            error("Macro is missing GetInputValues helper")
        end
        settings = loadstring(getter)()(tool)
    end)

    -- Always tear down, even on failure, so the user isn't left with a
    -- stranded preview clip on their timeline.
    teardown_preset_edit_session()

    if not ok then
        return { error = "Failed to capture preset settings: " .. tostring(err) }
    end

    dump(settings)
    return { settings = settings or {} }
end

function CancelPresetEdit()
    teardown_preset_edit_session()
    return { ok = true }
end

-- Minimal JSON helper to avoid crashes if `json` is unavailable
local function safe_json(obj)
    if json and json.encode then
        return json.encode(obj)
    end
    if obj and obj.message ~= nil then
        local msg = tostring(obj.message):gsub('"', '\\"')
        return '{"message":"' .. msg .. '"}'
    end
    return "{}"
end

pcall(ffi.cdef, [[
    unsigned long GetCurrentProcessId(void);
    uint64_t GetTickCount64(void);
    intptr_t ShellExecuteW(void*, const wchar_t*, const wchar_t*, const wchar_t*, const wchar_t*, int);
]])

-- A Workspace script runs in fuscript.exe, not necessarily in Resolve.exe.
pcall(ffi.cdef, [[
    typedef struct {
        unsigned long dwSize; unsigned long cntUsage; unsigned long th32ProcessID;
        uintptr_t th32DefaultHeapID; unsigned long th32ModuleID; unsigned long cntThreads;
        unsigned long th32ParentProcessID; long pcPriClassBase; unsigned long dwFlags;
        wchar_t szExeFile[260];
    } ACS_PROCESSENTRY32W;
    void* CreateToolhelp32Snapshot(unsigned long, unsigned long);
    int Process32FirstW(void*, ACS_PROCESSENTRY32W*);
    int Process32NextW(void*, ACS_PROCESSENTRY32W*);
    void* OpenProcess(unsigned long, int, unsigned long);
    unsigned long WaitForSingleObject(void*, unsigned long);
    int CloseHandle(void*);
    int WideCharToMultiByte(unsigned int, unsigned long, const wchar_t*, int, char*, int, const char*, int*);
]])
local acsKernel = ffi.load("kernel32")
local acsResolveHandle, acsResolvePid = nil, nil
local function process_name(entry)
    local chars = ffi.new("char[1024]")
    local n = acsKernel.WideCharToMultiByte(65001, 0, entry.szExeFile, -1, chars, 1024, nil, nil)
    return n > 0 and ffi.string(chars):lower() or ""
end

function InitResolveWatchdog()
    local snapshot = acsKernel.CreateToolhelp32Snapshot(2, 0)
    assert(snapshot ~= nil and ffi.cast("intptr_t", snapshot) ~= -1, "No se pudo leer la lista de procesos")
    local entry = ffi.new("ACS_PROCESSENTRY32W[1]")
    entry[0].dwSize = ffi.sizeof(entry[0])
    local processes = {}
    local ok = acsKernel.Process32FirstW(snapshot, entry)
    while ok ~= 0 do
        processes[tonumber(entry[0].th32ProcessID)] = {
            parent = tonumber(entry[0].th32ParentProcessID), name = process_name(entry[0])}
        ok = acsKernel.Process32NextW(snapshot, entry)
    end
    acsKernel.CloseHandle(snapshot)
    local pid = tonumber(ffi.C.GetCurrentProcessId())
    local visited = {}
    for _ = 1, 16 do
        local item = processes[pid]
        if not item or visited[pid] then break end
        if item.name == "resolve.exe" then acsResolvePid = pid; break end
        visited[pid] = true
        pid = item.parent
    end
    assert(acsResolvePid, "El host de scripting pertenece a una sesiÃ³n de Resolve que ya terminÃ³")
    acsResolveHandle = acsKernel.OpenProcess(1048576, 0, acsResolvePid)
    assert(acsResolveHandle ~= nil, "No se pudo vigilar el proceso real de Resolve")
    return true
end

function ResolveSessionAlive()
    return acsResolveHandle ~= nil and acsKernel.WaitForSingleObject(acsResolveHandle, 0) == 258
end

function CloseResolveWatchdog()
    if acsResolveHandle ~= nil then acsKernel.CloseHandle(acsResolveHandle); acsResolveHandle = nil end
end

function BridgeIdentity()
    return {resolvePid = acsResolvePid, hostPid = tonumber(ffi.C.GetCurrentProcessId()), bridgeVersion = 2}
end

local acsLauncher
local function process_launcher()
    if not acsLauncher then
        local root = main_app:match("^(.*)[\\/][^\\/]+$")
        local filename=join_path(root,"resources/modules/autocatchsubs_launch.lua")
        local chunk,reason=loadstring(read_file(filename),"@"..filename)
        assert(chunk,reason);acsLauncher=chunk()
    end
    return acsLauncher
end

function LaunchApp()
    local root = main_app:match("^(.*)[\\/][^\\/]+$")
    local backend = join_path(root,"AUTOCATCHSUBSBackend.exe")
    local host = tonumber(ffi.C.GetCurrentProcessId())
    local requestId = tostring(host).."-"..tostring(tonumber(ffi.C.GetTickCount64()))
    local parameters = '--host-pid '..host..' --request-id '..requestId
    local launcher=process_launcher()
    local process,problem=launcher.start(backend,parameters,root)
    if not process then
        print('[AUTOCATCHSUBS_ERROR] '..problem)
        print('[SYSTEM_INFO] Ejecuta '..join_path(root,'DIAGNOSTICO AUTOCATCHSUBS.cmd')..' y copia el informe. No requiere una licencia activa.')
        return false
    end
    local deadline = tonumber(ffi.C.GetTickCount64()) + 15000
    while tonumber(ffi.C.GetTickCount64()) < deadline do
        local ok,content=pcall(read_file,join_path(root,'state/launch-result.json'))
        if ok then
            local decoded,answer=pcall(json.decode,content)
            if decoded and answer and answer.request_id==requestId then
                launcher.close(process)
                if answer.opened then
                    print('[AUTOCATCHSUBS] Ventana visible confirmada; Resolve PID='..tostring(answer.resolve_pid)..'; interfaz PID='..tostring(answer.pid))
                    return true
                end
                print('[AUTOCATCHSUBS_ERROR] '..tostring(answer.error or answer.message or 'No se pudo mostrar la ventana'))
                return false
            end
        end
        local exited,code=launcher.exited(process)
        if exited then
            launcher.close(process)
            print('[AUTOCATCHSUBS_ERROR] El backend termino antes de confirmar la ventana; exit='..tostring(code)..'. Ejecuta DIAGNOSTICO AUTOCATCHSUBS.cmd.')
            return false
        end
        sleep(0.05)
    end
    launcher.close(process)
    print('[AUTOCATCHSUBS_ERROR] El backend inicio pero no confirmo la ventana en 15s. Ejecuta DIAGNOSTICO AUTOCATCHSUBS.cmd.')
    return false
end


local function handle_request(data)
    if type(data) ~= "table" then return {error=true, message="Invalid JSON"} end
    if data.func == "Ping" then
        local identity = BridgeIdentity()
        identity.message, identity.suite = "Pong", "AUTOCATCHSUBS"
        return identity
    end
    if data.func == "Exit" then return {message="Window closed; bridge stays available"} end
    if data.func == "GetTemplates" then return GetTemplates() end
    if data.func == "GetTemplateScanStatus" then return GetTemplateScanStatus() end
    if data.func == "ResetTemplateScan" then return ResetTemplateScan() end
    if data.func == "ExportTemplateCatalog" then return ExportTemplateCatalog() end
    project = projectManager:GetCurrentProject()
    mediaPool = project and project:GetMediaPool()
    if not project then return {error=true, message="Abre un proyecto en DaVinci Resolve"} end
    if data.func == "GetTimelineInfo" then return GetTimelineInfo()
    elseif data.func == "JumpToTime" then JumpToTime(data.seconds); return {message="Jumped to time"}
    elseif data.func == "ExportAudio" then return ExportAudio(data.outputDir, data.inputTracks, data.exportRange)
    elseif data.func == "GetExportProgress" then return GetExportProgress()
    elseif data.func == "CancelExport" then return CancelExport()
    elseif data.func == "CheckTrackConflicts" then return CheckTrackConflicts(data.filePath, data.trackIndex)
    elseif data.func == "AddSubtitles" then
        return {message="Job completed", result=AddSubtitles(data.filePath, data.trackIndex,
            data.templateName, data.conflictMode, data.presetSettings)}
    elseif data.func == "GeneratePreview" then
        return GeneratePreview(data.speaker, data.templateName, data.presetSettings, data.exportPath, data.language)
    elseif data.func == "StartPresetEdit" then return StartPresetEdit(data.initialSettings)
    elseif data.func == "CapturePresetSettings" then return CapturePresetSettings()
    elseif data.func == "CancelPresetEdit" then return CancelPresetEdit()
    end
    return {error=true, message="Unknown function", func=data.func}
end

function StartServer()
    InitResolveWatchdog()
    local info = assert(socket.find_first_address("127.0.0.1", PORT))
    local server = assert(socket.create(info.family, info.socket_type, info.protocol))
    server:set_blocking(false)
    server:set_option("nodelay", true, "tcp")
    -- Do not steal another server's port. Reopening only raises this duplicate's UI.
    local bound, err = server:bind(info)
    if not bound then
        server:close()
        if LaunchApp() then print("[SYSTEM_INFO] Se reutiliza el puente de esta sesiÃ³n y la ventana estÃ¡ visible.") end
        CloseResolveWatchdog()
        return
    end
    assert(server:listen())
    print("[SYSTEM_INFO] AUTOCATCHSUBS conectado a Resolve; puerto " .. PORT)
    LaunchApp()
    local pending = {}
    while ResolveSessionAlive() do
        local client = server:accept()
        if client then
            client:set_blocking(false)
            if #pending >= 16 then client:close()
            else pending[#pending+1] = {socket=client, request="", started=tonumber(ffi.C.GetTickCount64())} end
        end
        for index = #pending, 1, -1 do
            local entry = pending[index]
            local done = false
            if entry.response then
                local sent, reason = entry.socket:send(entry.response:sub(entry.offset))
                if sent then
                    entry.offset = entry.offset + sent
                    done = entry.offset > #entry.response
                elseif reason ~= "timeout" then done = true end
            else
                local chunk, reason = entry.socket:receive(64000)
                if chunk then entry.request = entry.request .. chunk
                elseif reason ~= "timeout" then done = true end
                local first, last = entry.request:find("\r\n\r\n", 1, true)
                if last then
                    local headers = entry.request:sub(1, first-1):lower()
                    local length = tonumber(headers:match("content%-length:%s*(%d+)")) or 0
                    if length > 4*1024*1024 then done = true
                    elseif #entry.request - last >= length then
                        local data = json.decode(entry.request:sub(last+1, last+length))
                        local ok, result = pcall(handle_request, data)
                        if not ok then
                            result = {error=true, message="Resolve handler failed", detail=tostring(result)}
                            print("[AUTOCATCHSUBS_ERROR] " .. tostring(result.detail))
                        end
                        local body = json.encode(result)
                        entry.response = create_response(body)
                        entry.offset = 1
                        entry.started = tonumber(ffi.C.GetTickCount64())
                    end
                end
            end
            if #entry.request > 4*1024*1024 or tonumber(ffi.C.GetTickCount64()) - entry.started > 3000 then done = true end
            if done then pcall(function() entry.socket:close() end); table.remove(pending, index) end
        end
        sleep(0.01)
    end
    for _, entry in ipairs(pending) do pcall(function() entry.socket:close() end) end
    server:close()
    CloseResolveWatchdog()
    print("[SYSTEM_INFO] Resolve terminÃ³; puente AUTOCATCHSUBS cerrado.")
end

local AutoSubs = {
    Init = function(self, executable_path, resources_folder, dev_mode)
        DEV_MODE = dev_mode
        if ffi.os == "Windows" then
            -- Define Windows API functions using FFI to prevent terminal opening
            ffi.cdef [[
                void Sleep(unsigned int ms);
                int ShellExecuteA(void* hwnd, const char* lpOperation, const char* lpFile, const char* lpParameters, const char* lpDirectory, int nShowCmd);
            ]]

            main_app = executable_path
            resources_path = resources_folder
            command_open = 'start "" "' .. main_app .. '"'
        else
            ffi.cdef [[
                int system(const char *command);
                struct timespec { long tv_sec; long tv_nsec; };
                int nanosleep(const struct timespec *req, struct timespec *rem);
            ]]

            if ffi.os == "OSX" then
                main_app = executable_path
                resources_path = resources_folder
                command_open = 'open ' .. main_app
            else -- Linux
                main_app = executable_path
                resources_path = resources_folder
                command_open = string.format("'%s' &", main_app)
            end
        end

        -- Set package path for module loading and import required modules
        local modules_path = join_path(resources_folder, "modules")
        package.path = join_path(modules_path, "?.lua") .. ";" .. package.path
        -- Load own modules through wide-character file APIs, including Windows
        -- profiles whose names contain accents. No global package loader changes.
        local function own_module(name)
            local filename=join_path(modules_path,name..".lua")
            local chunk,reason=loadstring(read_file(filename),"@"..filename)
            assert(chunk,reason)
            return chunk()
        end
        socket = own_module("ljsocket")
        json = own_module("dkjson")
        luaresolve = own_module("libavutil")
        font_fallback = own_module("font_fallback")

        assets_path = join_path(resources_path, "AutoSubs")
        StartServer()
    end
}

return AutoSubs
