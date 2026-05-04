@echo off
REM Dominian MCP Server - Windows Installer
REM Run this script from the dominian directory

echo ========================================
echo   Dominian MCP Server - Installer
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.10+ first.
    exit /b 1
)

echo [1/4] Checking Python...
python --version

REM Install MCP SDK
echo.
echo [2/4] Installing MCP SDK...
pip install "mcp>=1.0.0"

REM Install optional dependencies
echo.
echo [3/4] Installing optional dependencies...

REM Community detection
pip install networkx python-louvain >nul 2>&1
if %errorlevel%==0 (
    echo   - networkx + python-louvain (community detection)
) else (
    echo   - Skipping community detection
)

REM Tree-sitter
pip install tree-sitter >nul 2>&1
if %errorlevel%==0 (
    echo   - tree-sitter (deep parsing)
) else (
    echo   - Skipping tree-sitter
)

REM Verify imports
echo.
echo [4/4] Testing imports...
python -c "from database import GraphDatabase; from formatter import format_minimal; print('   All imports successful')" >nul 2>&1
if %errorlevel%==0 (
    echo   MCP server ready!
) else (
    echo   Import test failed - check dependencies
)

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo To start the MCP server:
echo   python server.py
echo.
echo For MCP client config, add to your config:
echo.
echo   {
echo     "mcpServers": {
echo       "dominian": {
echo         "command": "python",
echo         "args": ["PATH_TO\server.py"],
echo         "env": {
echo           "DOMINIAN_DB": ".dominian\agentgraph.db",
echo           "DOMINIAN_ROOT": "."
echo         }
echo       }
echo     }
echo   }
echo.
echo Replace PATH_TO with the actual path to dominian\
pause