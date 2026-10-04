-- AUTOCATCHSUBS installation-owned launcher. Resolve Free uses its embedded Lua host.
local root=[==[@INSTALL_ROOT@]==]
local ffi=ffi or require('ffi')
pcall(ffi.cdef, [[
int MultiByteToWideChar(unsigned int,unsigned long,const char*,int,wchar_t*,int);
void* _wfopen(const wchar_t*,const wchar_t*);
size_t fread(void*,size_t,size_t,void*);
int fclose(void*);
]])
local function wide(text)
    local buf=ffi.new('wchar_t[?]',#text+1)
    assert(ffi.C.MultiByteToWideChar(65001,0,text,-1,buf,#text+1)>0,'Invalid path')
    return buf
end
local resource=root..'/resources'
local module=resource..'/modules/autocatchsubs_core.lua'
local file=ffi.C._wfopen(wide(module),wide('rb'))
if file==nil then print('[AUTOCATCHSUBS_ERROR] Installation missing: '..module);return end
local parts={};local buf=ffi.new('char[65536]')
while true do local n=tonumber(ffi.C.fread(buf,1,65536,file));if n==0 then break end;parts[#parts+1]=ffi.string(buf,n) end
ffi.C.fclose(file)
local chunk,reason=loadstring(table.concat(parts),'@'..module)
if not chunk then print('[AUTOCATCHSUBS_ERROR] '..tostring(reason));return end
local ok,core=pcall(chunk)
if not ok then print('[AUTOCATCHSUBS_ERROR] '..tostring(core));return end
local started,problem=pcall(function()core:Init(root..'/AUTOCATCHSUBS.exe',resource,false)end)
if not started then print('[AUTOCATCHSUBS_ERROR] '..tostring(problem))end
