"""
Paratranz 术语获取
从 paratranz.cn API 获取项目的专有名词术语表
"""

import sys
import logging
import requests

logger = logging.getLogger(__name__)


def fetch(min_len: int = 0) -> list:
    """
    从 Paratranz 项目 6860 获取术语列表

    Args:
        min_len: 术语最小长度过滤

    Returns:
        [{"term": str, "translation": str, "note": str}, ...]
    """
    data = []
    for page in range(10):
        try:
            r = requests.get(
                f"https://paratranz.cn/api/projects/6860/terms",
                params={"pageSize": 800, "page": page + 1},
                timeout=15
            )
            r.raise_for_status()
            response_data = r.json()
        except requests.RequestException as e:
            logger.error(f"第 {page + 1} 页请求失败: {e}")
            if page == 0:
                raise  # 第一页就失败则完全失败
            break  # 后续页失败使用已有数据
        except ValueError as e:
            logger.error(f"第 {page + 1} 页JSON解析失败: {e}")
            break

        results = response_data.get('results', [])
        if len(results) == 0:
            break
        data.extend(results)
    else:
        logger.warning("可能还有更多数据未获取，已获取10页(8000条)")
        print('可能有更多数据，请增加页数', file=sys.stderr)

    result = [
        {
            'term': i.get('term', ''),
            'translation': i.get('translation', ''),
            'note': i.get('note', '')
        }
        for i in data
        if len(i.get('term', '')) >= min_len
    ]

    logger.info(f"从 Paratranz 获取了 {len(result)} 条术语")
    return result
