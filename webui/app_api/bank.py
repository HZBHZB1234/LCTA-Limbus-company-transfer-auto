# -*- coding: utf-8 -*-
"""LCTA_API 音频工具 mixin。"""
from webutils import (
    bank_dll_status, bank_set_dll_dir, bank_get_game_banks, bank_info,
    bank_extract, bank_rebuild, bank_export_rebank, bank_convert_mod,
    bank_patch_full, bank_rebank_info, bank_download_dlls,
)


class BankMixin:

    def bank_dll_status(self):
        return bank_dll_status()

    def bank_set_dll_dir(self, dll_dir):
        return bank_set_dll_dir(dll_dir)

    def bank_get_game_banks(self):
        return bank_get_game_banks()

    def bank_info(self, path):
        return bank_info(path)

    def bank_extract(self, bank_path, out_dir):
        return bank_extract(bank_path, out_dir)

    def bank_rebuild(self, bank_path, wav_dir, out_dir, format_id="vorbis", quality=92):
        return bank_rebuild(bank_path, wav_dir, out_dir, format_id, quality)

    def bank_export_rebank(self, original_path, modded_path, out_path, name, version,
                           author, desc, into_mod_folder):
        return bank_export_rebank(original_path, modded_path, out_path, name, version,
                                  author, desc, into_mod_folder)

    def bank_convert_mod(self, mod_name, keep_original=True):
        return bank_convert_mod(mod_name, keep_original)

    def bank_patch_full(self, rebank_path, bank_path, out_dir):
        return bank_patch_full(rebank_path, bank_path, out_dir)

    def bank_rebank_info(self, path):
        return bank_rebank_info(path)

    def bank_download_dlls(self, force=False):
        return bank_download_dlls(force)
