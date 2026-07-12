echo off
call .venv\Scripts\activate.bat
set TOP-LEVEL=%HOMEPATH%\PyCharmProjects\
set START-DIR=%TOP-LEVEL%assets\app\

nose2 -v -c nose2.cfg -s %START-DIR% -t %TOP-LEVEL%

pause
