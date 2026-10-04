-- Direct Windows process creation. Never elevates or changes security policy.
local ffi = require('ffi')
if not pcall(ffi.typeof,'ACS_STARTUPINFOW') then ffi.cdef [[
typedef struct {
 unsigned long cb; wchar_t *lpReserved, *lpDesktop, *lpTitle;
 unsigned long dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars;
 unsigned long dwFillAttribute, dwFlags; unsigned short wShowWindow, cbReserved2;
 unsigned char *lpReserved2; void *hStdInput, *hStdOutput, *hStdError;
} ACS_STARTUPINFOW;
typedef struct { void *hProcess, *hThread; unsigned long dwProcessId, dwThreadId; } ACS_PROCESS_INFORMATION;
int CreateProcessW(const wchar_t*, wchar_t*, void*, void*, int, unsigned long, void*, const wchar_t*, ACS_STARTUPINFOW*, ACS_PROCESS_INFORMATION*);
unsigned long GetLastError(void);
unsigned long GetFileAttributesW(const wchar_t*);
int MultiByteToWideChar(unsigned int,unsigned long,const char*,int,wchar_t*,int);
int GetExitCodeProcess(void*, unsigned long*);
int CloseHandle(void*);
unsigned long WaitForSingleObject(void*, unsigned long);
int TerminateProcess(void*, unsigned int);
]] end
local kernel = ffi.load('kernel32')
local M = {}
local function wide(text)
 local result=ffi.new('wchar_t[?]',#text+1)
 assert(kernel.MultiByteToWideChar(65001,0,text,-1,result,#text+1)>0,'Ruta UTF-8 invalida')
 return result
end
function M.describe(code)
 local reasons={
  [2]='No se encuentra el ejecutable. Reinstala el paquete completo.',
  [3]='La ruta de instalacion no existe. Reinstala desde esta cuenta de Windows.',
  [5]='Windows denego el acceso. Revisa el diagnostico y el historial de proteccion de Windows.',
  [193]='El ejecutable no es compatible o esta incompleto. Se requiere Windows x64.',
  [216]='Esta version requiere Windows x64.',
  [225]='Windows bloqueo el archivo por su proteccion antivirus. Revisa el historial de proteccion.',
  [226]='Windows retiro el archivo por su proteccion antivirus. Revisa el historial de proteccion.',
  [577]='Windows rechazo la firma del ejecutable. Revisa Control inteligente de aplicaciones.',
  [740]='El archivo requiere elevacion. Reinstala la version por usuario; no requiere administrador.',
  [1260]='Una politica de Windows impide ejecutar el archivo. Consulta al administrador de esa PC.'
 }
 return 'Win32='..tostring(code)..'; '..(reasons[code] or 'Fallo de inicio de Windows. Ejecuta DIAGNOSTICO AUTOCATCHSUBS.cmd.')
end
function M.start(executable, arguments, directory)
 local file=wide(executable)
 local attributes=tonumber(kernel.GetFileAttributesW(file))
 if attributes==4294967295 then
  local code=tonumber(kernel.GetLastError())
  return nil, M.describe(code)..'; archivo='..executable
 end
 if attributes%32>=16 then return nil,'La ruta del ejecutable es una carpeta: '..executable end
 -- Explicit application path prevents ambiguity in paths containing spaces.
 local command=wide('"'..executable..'"'..(arguments~='' and (' '..arguments) or ''))
 local cwd=wide(directory)
 local startup=ffi.new('ACS_STARTUPINFOW[1]')
 local process=ffi.new('ACS_PROCESS_INFORMATION[1]')
 startup[0].cb=ffi.sizeof(startup[0]);startup[0].dwFlags=1;startup[0].wShowWindow=0
 if kernel.CreateProcessW(file,command,nil,nil,0,0x08000000,nil,cwd,startup,process)==0 then
  local code=tonumber(kernel.GetLastError())
  return nil,M.describe(code)..'; archivo='..executable
 end
 kernel.CloseHandle(process[0].hThread)
 return {handle=process[0].hProcess,pid=tonumber(process[0].dwProcessId)}
end
function M.exited(process)
 if kernel.WaitForSingleObject(process.handle,0)==258 then return false end
 local code=ffi.new('unsigned long[1]')
 if kernel.GetExitCodeProcess(process.handle,code)==0 then return true,-1 end
 return true,tonumber(code[0])
end
function M.wait(process,timeout)
 return tonumber(kernel.WaitForSingleObject(process.handle,timeout))==0
end
function M.terminate(process,code) kernel.TerminateProcess(process.handle,code) end
function M.close(process)
 if process and process.handle~=nil then kernel.CloseHandle(process.handle);process.handle=nil end
end
return M
