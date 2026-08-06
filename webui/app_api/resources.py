# -*- coding: utf-8 -*-
"""LCTA_API 官方资源预下载：转发到 ResourceUpdaterAPI。"""

class ResourceMixin:

    def resource_updater_get_initial_state(self):
        return self.resource_updater_api.get_initial_state()

    def resource_updater_probe_game_dir(self, game_dir):
        return self.resource_updater_api.probe_game_dir(game_dir)

    def resource_updater_save_options(self, options):
        return self.resource_updater_api.save_options(options)

    def resource_updater_start_update(self, options):
        return self.resource_updater_api.start_update(options)

    def resource_updater_cancel_update(self):
        return self.resource_updater_api.cancel_update()
