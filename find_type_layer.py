import json
import jsonpatch
import os
import shutil
import zipfile
class find_type_layer:
    def __init__(self,config,log):
        self.log=log
        self.config=config
        try:
            if os.path.exists('temp'):
                shutil.rmtree('temp')
        except Exception as e:
            self.log(str(e))
            raise
        os.makedirs('temp')
        if self.config.get('backup_enabled',False):
            self.log(f"根据备份进行优化，正在解压文件")