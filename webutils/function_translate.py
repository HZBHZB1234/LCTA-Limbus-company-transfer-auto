import os
import time
import json
from pathlib import Path
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from typing import Callable
from translateFunc.translate_main import *
from translateFunc.translate_doc import *
from translateFunc.translate_request import *
from translateFunc.get_proper import fetch as fetch_proper
from translatekit import *
from webutils.log_manage import LogManager
from webutils.functions import get_cache_font, zip_folder

def translate_main(modal_id, logger_: LogManager,
                   whole_configs: dict, translator_config: dict,
                   formating_function: Callable[[dict, dict], dict],):
    with tempfile.TemporaryDirectory() as tmpdir:
        logger_.log_modal_process("开始初始化", modal_id)
        logger_.log_modal_status("正在初始化", modal_id)
        
        tmp = Path(tmpdir)
            
        target_dir = tmp / "LLc-CN-LCTA"
        target_dir.mkdir()
        
        configs: dict = whole_configs.get('ui_default', {}).get('translator', {})
            
        is_text = configs.get("is_text", True)
        translator_text = configs.get("translator", "Linguee翻译服务")
        fallback = configs.get("fallback", True)
        enable_proper = configs.get("enable_proper", True)
        auto_fetch_proper = configs.get("auto_fetch_proper", True)
        proper_path = configs.get("proper_path", "")
        enable_role = configs.get("enable_role", True)
        enable_skill = configs.get("enable_skill", True)
        enable_dev_settings = configs.get("enable_dev_settings", True)
        kr_path = configs.get("kr_path", "")
        jp_path = configs.get("jp_path", "")
        llc_path = configs.get("llc_path", "")
        en_path = configs.get("en_path", "")
        from_lang = configs.get("from_lang", "EN")
        HAS_PREFIX = configs.get("has_prefix", True) or not enable_dev_settings
        is_llm = translator_text == "LLM通用翻译服务"
        api_settings = translator_config.get(translator_text, {})
        dump = os.getenv('DUMP', 'False').lower() == 'true'
        def dump(content):
            if dump:
                logger_.log(content)
        
        game_path = Path(whole_configs.get("game_path", ""))
        
        debug_mode = whole_configs.get("debug", False)
        @contextmanager
        def protect_secret():
            if not debug_mode:
                logger_c = logging.getLogger('translatekit')
                logger_c.setLevel(logging.INFO)
            yield
            if not debug_mode:
                logger_c.setLevel(logging.DEBUG)
        
        if is_llm:
            api_settings['system_prompt'] = TEXT_SYSTEM_PROMPT \
                if is_text else JSON_SYSTEM_PROMPT
            api_settings['response_format'] = "text" \
                if is_text else "json_object"
        
        
        translator: TranslatorBase = TRANSLATOR_TRANS[translator_text]
        
        api_settings = formating_function(api_settings, translator)
        
        translate_config = TranslationConfig(
            api_setting=api_settings,
            debug_mode=True,
            enable_cache=True,
            enable_metrics=True
        )
        
        if is_llm:
            translate_config.text_max_length = 20000
            translate_config.max_workers = 1
            
        with protect_secret():
            translator: TranslatorBase = translator(translate_config)
        
        lang_path = game_path / 'LimbusCompany_Data' / "lang"
        assets_path = game_path / "LimbusCompany_Data" / "Assets" /\
            "Resources_moved" / "Localize"
        
        if not kr_path or not enable_dev_settings:
            kr_path = assets_path / "kr"
        if not jp_path or not enable_dev_settings:
            jp_path = assets_path / "jp"
        if not en_path or not enable_dev_settings:
            en_path = assets_path / "en"
        if not llc_path or not enable_dev_settings:
            llc_path = lang_path / "LLC_zh-CN"


        base_path_config = PathConfig(
            target_path=target_dir,
            llc_base_path=llc_path,
            KR_base_path=kr_path,
            JP_base_path=jp_path,
            EN_base_path=en_path
        )
        dump(base_path_config)
        
        request_config = RequestConfig(
            enable_proper=True,
            enable_role=True,
            enable_skill=True,
            is_text_format=is_text,
            is_llm=is_llm,
            translator=translator,
            from_lang=from_lang,
            save_result=True
        )
        
        base_path_config.create_need_dirs()
        target_files = list(base_path_config.KR_base_path.rglob("*.json"))
        dump(target_files)
        len_target_file = len(target_files)
        logger_.log(f"找到 {len_target_file} 个文件。")
        logger_.log_modal_process(f"找到 {len_target_file} 个文件。", modal_id)
        try:
            if HAS_PREFIX:
                model_file = base_path_config.KR_base_path / \
                    "KR_ScenarioModelCodes-AutoCreated.json"
                keyword_file = base_path_config.KR_base_path / \
                    "KR_BattleKeywords.json"
            else:
                model_file = base_path_config.KR_base_path / \
                    "ScenarioModelCodes-AutoCreated.json"
                keyword_file = base_path_config.KR_base_path / \
                    "BattleKeywords.json"
            target_files.remove(model_file)
            target_files.remove(keyword_file)
            target_files.insert(0, model_file)
            target_files.insert(0, keyword_file)
        except Exception as e:
            logger_.log_error(e)
            logger_.log_modal_process(f"警告: 移动特殊文件失败: {str(e)}", modal_id)
        
        matcher = MatcherOrganizer()
        
        if enable_proper:
            if auto_fetch_proper:
                proper_data = fetch_proper()
            else:
                proper_path = Path(proper_path)
                proper_data = json.loads(proper_path.read_text(encoding="utf-8"))
        
            matcher.update_proper(proper_data)
        
        logger_.log_modal_status("正在执行翻译...", modal_id)
        logger_.update_modal_progress(10, "正在执行翻译...", modal_id)
        logger_.log_modal_process("开始执行翻译...", modal_id)
        
        for idx, file in enumerate(target_files):
            file_path_config = FilePathConfig(
                KR_path=file,
                _PathConfig=base_path_config,
                has_prefix=HAS_PREFIX
            )
            
            processer = FileProcessor(
                path_config=file_path_config,
                matcher=matcher,
                request_config=request_config,
                logger=logger
            )
            
            try:
                try:
                    processer.process_file()
                except ProcesserExit as e:
                    logger.info(f"文件{file_path_config.rel_path}处理完毕，退出码{e.exit_type} ")
                    if not e.exit_type == 'already_translated':
                        logger_.log_modal_process(f"文件{file_path_config.rel_path}处理完毕，退出码{e.exit_type} ", modal_id)
                        logger_.update_modal_progress(int(10+(idx//len_target_file)/4*5),
                                                      f"文件{file_path_config.real_name}操作完成", modal_id)
                        logger_.check_running(modal_id)
                    if e.exit_type == 'translation_length_error':
                        raise
            except Exception as e:
                logger.error(f"文件{file_path_config.rel_path}处理出错，错误信息：{e}")
                logger.exception(e)
                logger_.log_modal_process(f"文件{file_path_config.rel_path}处理出错，错误信息：{e}", modal_id)
                if fallback and is_llm:
                    try:
                        logger.info('尝试切换请求格式')
                        logger_.log_modal_process('尝试切换请求格式', modal_id)
                        translator.update_config(
                            system_prompt=JSON_SYSTEM_PROMPT if is_text else TEXT_SYSTEM_PROMPT,
                            response_format="json_object" if is_text else "text")
                        request_config.is_text_format = not is_text
                        processer = FileProcessor(
                            path_config=file_path_config,
                            matcher=matcher,
                            request_config=request_config,
                            logger=logger
                        )
                        try:
                            processer.process_file()
                        except ProcesserExit as e:
                            logger.info(f"文件{file_path_config.rel_path}处理完毕，退出码{e.exit_type} ")
                    except Exception as e:
                        logger.error(f"文件{file_path_config.rel_path}处理出错，切换后任然失败。错误信息：{e}")
                        logger.exception(e)
                    finally:
                        request_config.is_text_format = is_text
                        translator.update_config(
                            system_prompt=TEXT_SYSTEM_PROMPT if is_text else JSON_SYSTEM_PROMPT,
                            response_format="text" if is_text else "json_object")
            
            if file_path_config.KR_path == model_file and enable_role:
                matcher.update_models(kr_role=json.loads(
                        file_path_config.KR_path.read_text(encoding='utf-8-sig')),
                    cn_role=json.loads(
                        file_path_config.target_file.read_text(encoding='utf-8-sig')))
                
            if file_path_config.KR_path == keyword_file and enable_skill:
                matcher.update_efects(KRaffect=json.loads(
                        file_path_config.KR_path.read_text(encoding='utf-8-sig')),
                    CNaffect=json.loads(
                        file_path_config.target_file.read_text(encoding='utf-8-sig')))
        logger_.log_modal_process("已完成汉化", modal_id)
        logger_.update_modal_progress(90, "已完成汉化", modal_id)

        usage = translator.get_performance_metrics()
        logger_.log_modal_process(f"""翻译完成，本次翻译开销:
请求数量: {usage.get('request_count', '获取失败')}
请求字符数: {usage.get('chars_translated', '获取失败')}""", modal_id)
        logger_.log_modal_process("开始打包...", modal_id)
        logger_.log_modal_status('正在打包汉化包', modal_id)
        
        
        today = datetime.now()
        current_date = today.strftime("%Y%m%d")  # 格式：YYYYMMDD

        work_dir = Path(os.getcwd())
        previous_version = 1999010101
        zips = work_dir.glob(f"{current_date}??.zip")
        
        for i in zips:
            with suppress(Exception):
                if int(str(i)[:-4]) > previous_version:
                    previous_version = int(str(i)[:-4])

        try:
            # 提取上一个版本号的日期部分和序号部分
            prev_date = str(previous_version)[:8]  # 前8位是日期
            prev_sequence = str(previous_version[8:])  # 后2位是序号
            
            if prev_date == current_date:
                # 如果是同一天，序号加1
                new_sequence = prev_sequence + 1
                # 确保序号是两位数（01-99）
                if new_sequence > 99:
                    raise ValueError("当日版本序号已超过99，请使用新的日期")
                VERSION = f"{current_date}{new_sequence:02d}"
            else:
                # 如果是新的一天，从01开始
                VERSION = f"{current_date}01"
        except Exception:
            logger.error(f"警告: 上一个版本号'{previous_version}'格式不正确，将重置为今天的新版本")
            VERSION = f"{current_date}01"

        try:
            Info_path = target_dir / "Info"
            Info_path.mkdir(parents=True, exist_ok=True)
            license_project = llc_path / "Info" / "LICENSE"
            license_target = Info_path / "LICENSE"
            shutil.copy(license_project, license_target)
            version_target = Info_path / "version.json"
            version_target.write_text(json.dumps(
                {"version": VERSION, "notice": "本次文本更新没有提示。"},
                ensure_ascii=False, indent=4))
        except Exception as e:
            logger.error('创建版本信息失败')
            logger.exception(e)
            
        try:
            font_project = get_cache_font(whole_configs, logger_)
            font_target = target_dir / 'Fonts' / 'Context'
            font_target.mkdir(parents=True, exist_ok=True)
            font_target = font_target / 'ChineseFont.ttf'
            shutil.copy(font_project, font_target)
        except Exception as e:
            logger.error('复制字体文件失败')
            logger.exception(e)
            logger_.log_modal_process(f"复制字体文件失败: {str(e)}", modal_id)
            
        r = zip_folder(target_dir, work_dir / f'LCTA_{VERSION}.zip', logger_)
        if r:
            logger_.log_modal_process("压缩完成", modal_id)
            logger_.log_modal_status("翻译完成", modal_id)
            logger_.update_modal_progress(100, "全部操作完成", modal_id)
        else:
            logger_.log_modal_process("压缩失败", modal_id)
            logger_.log_modal_status("操作失败", modal_id)
            logger_.update_modal_progress(100, "操作失败", modal_id)
            os.system(f'explorer "{tmp}"')
            logger_.log_modal_process('目前已打开产物文件夹，如果有需要，请在60秒内保存数据', modal_id)
            time.sleep(60)

