import type {
  StartupData, ApiResult, ApiDataResult, ApiPackagesResult, TranslationConfig, PackageInfo,
  InstalledPackages, InstalledMods, CdnStatus, SpeedStatus,
  UpdateInfo, FancyRulesets, FontInfo, SymlinkStatus, FileDropInfo,
} from './config'

export interface PyWebViewApi {
  get_startup_data(): Promise<StartupData>

  get_config_value(key_path: string, default_value?: unknown): Promise<unknown>
  get_config_batch(key_paths: string[]): Promise<{ config_values: Record<string, unknown> }>
  update_config_value(key_path: string, value: unknown, create_missing?: boolean): Promise<ApiResult>
  update_config_batch(config_updates: Record<string, unknown>): Promise<{ updated: number; total: number }>
  save_config_to_file(): Promise<boolean>
  get_attr(attr_name: string): Promise<unknown>
  set_attr(attr_name: string, value: unknown): Promise<void>

  save_settings(game_path: string, debug_mode: boolean, auto_update: boolean): Promise<void>
  use_default_config(): Promise<void>
  reset_config(): Promise<void>
  use_inner(): Promise<void>
  use_default(): Promise<void>

  run_func(func_name: string, ...args: unknown[]): Promise<unknown>

  log(message: string): Promise<void>
  log_error(e: string): Promise<void>
  log_ui(message: string, level?: number): Promise<void>

  update_progress(percent: number, text: string): Promise<void>
  progress_callback(progress: number): Promise<boolean>

  add_modal_id(modal_id: string): Promise<void>
  add_modal_log(message: string, modal_id: string): Promise<void>
  update_modal_progress(percent: number, text: string, modal_id: string, log?: boolean): Promise<void>
  set_modal_status(status: string, modal_id: string): Promise<void>
  check_modal_running(modal_id: string, log?: boolean): Promise<void>
  set_modal_running(modal_id: string, types?: string): Promise<void>
  del_modal_list(modal_id: string): Promise<void>

  start_translation(translator_config: TranslationConfig, modal_id?: string): Promise<ApiResult>
  test_api(key: string, api_settings: Record<string, unknown>): Promise<ApiResult>
  format_api_settings(api_settings: Record<string, unknown>, translator: string): Promise<Record<string, unknown>>

  get_translation_packages(): Promise<ApiPackagesResult<PackageInfo>>
  delete_translation_package(package_name: string): Promise<ApiResult>
  install_translation(package_name: string, modal_id?: string): Promise<ApiResult>
  toggle_installed_package(able: boolean): Promise<ApiResult>
  get_installed_packages(): Promise<InstalledPackages>
  delete_installed_package(package_name: string): Promise<ApiResult>
  use_translation(package_name: string, modal_id?: string): Promise<ApiResult>
  change_font_for_package(package_name: string, font_path: string, modal_id?: string): Promise<ApiResult>

  download_ourplay_translation(modal_id?: string): Promise<ApiResult>
  download_llc_translation(modal_id?: string): Promise<ApiResult>
  download_LCTA_auto(modal_id?: string): Promise<ApiResult>
  download_bubble(modal_id?: string): Promise<ApiResult>
  fetch_proper_nouns(modal_id?: string): Promise<ApiResult>

  find_installed_mod(): Promise<InstalledMods>
  toggle_mod(mod_name: string, enable: boolean): Promise<ApiResult>
  delete_mod(mod_name: string, enable: boolean): Promise<ApiResult>
  open_mod_path(): Promise<void>

  get_system_fonts_list(): Promise<{ fonts: FontInfo[] }>
  export_selected_font(font_name: string, destination_path: string): Promise<ApiResult>

  cdn_get_status(): Promise<ApiDataResult<CdnStatus>>
  cdn_optimize_cloudflare(modal_id?: string): Promise<ApiResult>
  cdn_optimize_cloudfront(modal_id?: string): Promise<ApiResult>
  cdn_full_optimization(modal_id?: string): Promise<ApiResult>
  cdn_write_hosts(cf_ip?: string, cloudfront_mappings?: Array<{ domain: string; ip: string }>, modal_id?: string): Promise<ApiResult>
  cdn_remove_cloudflare(): Promise<ApiResult>
  cdn_remove_cloudfront(): Promise<ApiResult>

  speed_get_status(): Promise<ApiDataResult<SpeedStatus>>
  speed_inject(): Promise<ApiResult>
  speed_eject(): Promise<ApiResult>
  speed_set(factor: number): Promise<ApiResult>
  speed_enable(): Promise<ApiResult>
  speed_disable(): Promise<ApiResult>

  auto_check_update(): Promise<void>
  manual_check_update(): Promise<UpdateInfo>
  perform_update_in_modal(modal_id: string): Promise<ApiResult>
  perform_update_from_file(file_path: string, modal_id?: string): Promise<ApiResult>

  browse_file(input_id: string): Promise<void>
  browse_folder(input_id: string): Promise<void>

  handle_dropped_files(files_data: string[]): Promise<FileDropInfo>
  eval_dropped_files(files_data: string[], modal_id?: string): Promise<ApiResult>

  get_fancy_rulesets(): Promise<ApiDataResult<FancyRulesets>>
  fancy_main(config_list: FancyRulesets['builtin'], enableMap: Record<string, boolean>): Promise<ApiResult>

  get_symlink_status(): Promise<SymlinkStatus>
  move_folders(from_path: string, target_path: string): Promise<ApiResult>

  clean_cache(modal_id: string, custom_files: string[], clean_progress: boolean, clean_notice: boolean, clean_mods: boolean): Promise<ApiResult>

  init_github(): Promise<void>
  init_cache(): Promise<void>
  init_log(): Promise<void>
  check_show(): Promise<{ show: boolean; message: string }>
  resetElder(): Promise<void>
  save_setting_from(): Promise<void>
  startTest(): Promise<void>
  eval_skip(): Promise<void>
  sign_eval_js(): Promise<void>
}
