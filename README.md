# auto-bow-mount-v7

Windows GUI automation tool rewritten from an original 按键精灵 `.Q` script.

## What it does

- Runs the bow/mount loop with configurable delays
- Supports random jitter
- Supports repeated small cycles and big-cycle waiting
- Supports optional daily 4:00 card-skip click
- Saves configuration as `auto_bow_mount_config.json`

## Main file

- `auto_bow_mount_gui.py`

## Default values

- first loop delay: `2`
- tab delay: `1`
- action delay: `1`
- before mount delay: `2`
- ride duration: `12`
- between small cycles: `3`
- between big cycles: `2`
- jitter range: `1000-2500 ms`
- salute key: `2`
- small cycle count: `10`
- daily skip: `off`

## Build

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --name 自动鞠躬骑乘_v7 auto_bow_mount_gui.py
```

## Note

Run the program as Administrator if the target game is also running as Administrator.

Author: `@f`  
GitHub: `https://github.com/futuer-szd`
