# Project Encoding Rule

- `build.ps1` MUST be encoded as **UTF-8 with BOM**. The script contains Chinese
  text; PowerShell on Windows requires BOM to decode it correctly. After editing
  with the Write tool (which writes UTF-8 without BOM), always restore the BOM
  afterward: `printf '\xef\xbb\xbf' > tmp && cat build.ps1 >> tmp && mv tmp build.ps1`
