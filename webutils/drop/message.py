from pathlib import Path
from collections.abc import Mapping

from .handlers import REGISTRY


def makeMessage(content: Mapping[str, str]) -> str:
    labels = REGISTRY.labels()
    message = '<div>'
    count: dict[str, int] = {key: 0 for key in labels}
    for i in content.values():
        count[i] += 1
    for key, value in count.items():
        if value > 0:
            message += f"<p>{labels.get(key, key)}: {value}个</p>"
    message += '<br/><hr /><br/>'
    message += '<details><summary>点击展开完整列表</summary><br />'

    for i, t in content.items():
        message += f'<p><strong>{Path(i).name}</strong>: {labels.get(t, t)}</p>'
    message += '</details><br /><hr /><br />'
    message += '<p>点击确认以安装</p>'
    message += '</div>'
    if count['update'] and not all(count[key] == 0 for key in count if key != 'update'):
        return 'invalid'
    if all(count[key] == 0 for key in count if key != 'invalid') and count['invalid'] > 0:
        return 'none'
    return message
