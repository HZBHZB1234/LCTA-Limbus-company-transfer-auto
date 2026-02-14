import glob
import logging
import os
import shutil
import time
import shlex
from pathlib import Path
from threading import Thread

from launcher.modfolder import get_mod_folder

_game_path = None
def sound_folder():
    return Path(_game_path).parent / "LimbusCompany_Data/StreamingAssets/Assets/Sound/FMODBuilds/Desktop"

def sound_data_paths():
    return map(os.path.normpath, glob.glob(str(sound_folder()) + "/*.bank"))

def smallest_sound_file():
    return min(sound_data_paths(), key=os.path.getsize)

def wait_for_validation():
    smallest = smallest_sound_file()
    os.remove(smallest)
    while not os.path.exists(smallest):
        time.sleep(0.1)

def sound_replace_thread(mod_folder: str):
    wait_for_validation()

    logging.info("Validation complete, replacing sound files")
    target_folder = sound_folder()
    for sound_file in glob.glob(f"{mod_folder}/*.bank"):
        logging.info("Replacing %s", sound_file)
        target = os.path.join(target_folder, os.path.basename(sound_file))
        os.replace(target, target + ".bak")
        shutil.copyfile(sound_file, target)

def restore_sound():
    target_folder = sound_folder()
    for sound_file in glob.glob(f"{target_folder}/*.bank.bak"):
        target = sound_file.replace(".bak", "")
        os.replace(sound_file, target)

def replace_sound(mod_folder: str, game_path: str):
    mod_zips_root_path = os.environ['mod_path']
    global _game_path
    _game_path = shlex.split(game_path)[0]
    if any(file_name.endswith(".bank") for file_name in os.listdir(mod_zips_root_path)):
        Thread(target=sound_replace_thread, args=(mod_folder,)).start()
    else:
        logging.info("No .bank found, skip sound replacing process.")