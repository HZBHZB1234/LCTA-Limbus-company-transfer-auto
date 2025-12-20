import requests
import json

WEBNOTE_HEADERS={
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0',
    'Referer':'https://webnote.cc/',
    'Origin':'https://webnote.cc/',
    'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
    'Accept':'application/json, text/javascript, */*; q=0.01',
    'Accept-Encoding':'gzip, deflate, br, zstd',
    'Accept-Language':'en-US,en;q=0.9',
    'Sec-Ch-Ua':'"Chromium";v="140", "Not=A?Brand";v="24", "Microsoft Edge";v="140"',
    'Sec-Ch-Ua-Mobile':'?0',
    'Sec-Ch-Ua-Platform':'"Windows"',
    'Sec-Fetch-Dest':'empty',
    'Sec-Fetch-Mode':'cors',
    'Sec-Fetch-Site':'cross-site',
    }
API_URL = "https://api.txttool.cn/netcut/note"

class Note():
    ONE_HOUR = 3600
    SIX_HOUR = 21600
    ONE_DAY = 86400
    THREE_DAY = 259200
    ONE_WEEK = 604800
    ONE_MONTH = 2592000
    THREE_MONTH = 7776000
    SIX_MONTH = 15552000
    ONE_YEAR = 31536000
    TWO_YEAR = 63072000
    THREE_YEAR = 94608000
    def __init__(self, address, pwd="", read_only=False):
        self.note_name = address
        self.pwd = pwd
        self.note_url = f'webnote.cc/{self.note_name}'
        self.read_only = read_only
        
    def fetch_note_info(self):
        if self.read_only:
            self._fetch_note_info_ReadOnly()
        else:
            self._fetch_note_info_write()
    
    def _fetch_note_info_write(self):
        fetch_request = requests.post(f'{API_URL}/info',
                                     headers=WEBNOTE_HEADERS, data={'note_name': self.note_name, "note_pwd": self.pwd})
        fetch_request.raise_for_status()
        note_info = fetch_request.json()
        
        if not str(note_info['status']) == '1':
            raise ValueError(f"无法获取笔记信息，状态码: {note_info['status']}")
        
        note_data = note_info['data']
        self.created_time = note_data['created_time']
        self.expire_time = note_data['expire_time']
        self.last_read_time = note_data['last_read_time']
        self.log_list = note_data['log_list']
        self.note_content = note_data['note_content']
        self.note_id = note_data['note_id']
        self.note_token = note_data['note_token']
        self.read_count = note_data['read_count']
        self.updated_time = note_data['updated_time']
        
        return note_data

    def _fetch_note_info_ReadOnly(self):
        fetch_request = requests.post(f'{API_URL}/info',
                                     headers=WEBNOTE_HEADERS, data={'note_id': self.note_name, "note_pwd": self.pwd})
        fetch_request.raise_for_status()
        note_info = fetch_request.json()
        
        if not str(note_info['status']) == '1':
            raise ValueError(f"无法获取笔记信息，状态码: {note_info['status']}")
        
        note_data = note_info['data']
        self.created_time = note_data['created_time']
        self.expire_time = note_data['expire_time']
        self.note_content = note_data['note_content']
        self.note_id = note_data['note_id']
        self.note_token = note_data['note_token']
        self.updated_time = note_data['updated_time']
        
        return note_data
    def update_note_content(self, new_content):
        update_request = requests.post(f'{API_URL}/save',
                                       headers=WEBNOTE_HEADERS,
                                       data={
                                           'note_name': self.note_name,
                                           'note_id': self.note_id,
                                           'note_token': self.note_token,
                                           'expire_time': self.expire_time,
                                           'note_content': new_content,
                                           'note_pwd': self.pwd
                                       })
        update_request.raise_for_status()
        update_response = update_request.json()
        
        if not str(update_response['status']) == '1':
            raise ValueError(f"无法更新笔记内容，状态码: {update_response['status']}")
        
        return update_response