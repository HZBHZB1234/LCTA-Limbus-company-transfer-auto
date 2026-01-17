import requests
import time
from pathlib import Path

class UpFileClient:
    def __init__(self):
        self.base_url = "https://upfile.live"
        self.session = requests.Session()
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/zh-cn/',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        })

    def get_upload_link(self, file_name):
        """获取上传链接"""
        url = f"{self.base_url}/api/file/getUploadLink/"
        data = {
            'vipCode': '',
            'file_name': file_name
        }
        
        response = self.session.post(url, data=data)
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 1:
                return result['data']
            else:
                raise Exception(f"获取上传链接失败: {result}")
        else:
            raise Exception(f"HTTP错误: {response.status_code}")

    def upload_file(self, upload_url, file_path):
        """实际上传文件到云存储"""
        file_name = Path(file_path).name
        
        with open(file_path, 'rb') as file:
            file_content = file.read()
        
        headers = {
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': f'attachment; filename="{file_name}"'
        }
        
        # 注意：这里使用PUT方法
        response = requests.put(upload_url, data=file_content, headers=headers)
        
        # 云存储通常返回204或200，但没有响应体是正常的
        if response.status_code in [200, 204]:
            return True
        else:
            raise Exception(f"文件上传失败: {response.status_code}")

    def confirm_upload(self, file_size, file_name, file_key):
        """确认上传完成"""
        url = f"{self.base_url}/api/file/upload/"
        data = {
            'file_size': file_size,
            'file_name': file_name,
            'file_key': file_key
        }
        
        response = self.session.post(url, data=data)
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 1:
                return result['data']  # 返回文件ID等信息
            else:
                raise Exception(f"确认上传失败: {result}")
        else:
            raise Exception(f"HTTP错误: {response.status_code}")

    def get_file_info(self, file_id):
        """获取文件信息"""
        url = f"{self.base_url}/api/file/info/"
        params = {
            'file_id': file_id,
            '_': int(time.time() * 1000)  # 添加时间戳防止缓存
        }
        
        response = self.session.get(url, params=params)
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 1:
                return result['data']
            else:
                raise Exception(f"获取文件信息失败: {result}")
        else:
            raise Exception(f"HTTP错误: {response.status_code}")

    def download_file(self, file_id, save_path=None):
        """下载文件"""
        try:
            # 1. 获取文件信息
            file_info = self.get_file_info(file_id)
            file_name = file_info['file_name']
            
            if save_path is None:
                save_path = file_name
            elif Path(save_path).is_dir():
                save_path = str(Path(save_path) / file_name)
            
            # 2. 获取下载重定向链接
            download_url = f"{self.base_url}/download/{file_id}/"

            response = self.session.get(download_url, allow_redirects=True)
            
            if response.status_code == 200:
                with open(save_path, 'wb') as file:
                    file.write(response.content)
                
                file_size = Path(save_path).stat().st_size
                
                return {
                    'success': True,
                    'file_path': save_path,
                    'file_size': file_size,
                    'file_name': file_name
                }
            else:
                raise Exception(f"下载失败，状态码: {response.status_code}")
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def delete_file(self, file_id):
        """删除文件"""
        try:
            url = f"{self.base_url}/api/file/delete/"
            data = {
                'file_id': file_id
            }
            
            response = self.session.post(url, data=data)
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    return {
                        'success': True,
                        'file_id': file_id
                    }
                else:
                    raise Exception(f"删除失败: {result}")
            else:
                raise Exception(f"HTTP错误: {response.status_code}")
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def upload(self, file_path, log_function=print):
        """主上传方法"""
        try:
            file_path_obj = Path(file_path)
            file_name = file_path_obj.name
            file_size = file_path_obj.stat().st_size
            
            log_function(f"开始上传文件: {file_name} ({file_size} bytes)")
            
            # 1. 获取上传链接
            log_function("步骤1: 获取上传链接...")
            upload_data = self.get_upload_link(file_name)
            upload_url = upload_data['upload_url']
            file_key = upload_data['file_key']
            log_function(f"获取到上传链接")
            
            # 2. 上传文件到云存储
            log_function("步骤2: 上传文件到云存储...")
            self.upload_file(upload_url, file_path)
            log_function("文件上传成功")
            
            # 3. 确认上传
            log_function("步骤3: 确认上传...")
            confirm_data = self.confirm_upload(file_size, file_name, file_key)
            file_id = confirm_data['file_id']
            log_function(f"上传确认成功，文件ID: {file_id}")
            
            # 4. 获取文件信息
            log_function("步骤4: 获取文件信息...")
            file_info = self.get_file_info(file_id)
            log_function(f"文件信息获取成功")
            
            return {
                'success': True,
                'file_id': file_id,
                'file_info': file_info,
                'download_url': f"{self.base_url}/zh-cn/files/{file_id}",
                'direct_download_url': f"{self.base_url}/download/{file_id}/"
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }