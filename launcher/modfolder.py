import os


def get_mod_folder():
    if appdata := os.getenv("APPDATA"):
        return os.path.join(appdata, "LimbusCompanyMods")
    else:
        raise Exception("APPDATA not found")
