# -*- coding: utf-8 -*-
"""LCTA_API 官方资源预下载与官服/lethe 资源切换：转发到对应页面控制器。"""

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

    # ---- 官服 ⇄ lethe 资源切换 ----

    def server_switch_get_initial_state(self):
        return self.server_switch_api.get_initial_state()

    def server_switch_probe_lethe_dir(self, lethe_dir):
        return self.server_switch_api.probe_lethe_dir(lethe_dir)

    def server_switch_save_options(self, options):
        return self.server_switch_api.save_options(options)

    def server_switch_create_shortcut(self, lethe_dir):
        return self.server_switch_api.create_shortcut(lethe_dir)
