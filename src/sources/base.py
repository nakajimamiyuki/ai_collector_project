"""
BaseSource —— 所有信息源的抽象基类 (v2.0)

设计目标
--------
把「如何发现某个数据源的新内容」这件事统一成一个接口，让 Monitor
无需关心具体源是 B 站、arXiv 还是知乎。新增一个源 = 写一个子类，
实现 fetch_new_urls()，对 Monitor / DBManager / Pipeline 零侵入。

契约
----
每个子类必须：
  1. 设置类属性 source_type（唯一标识，如 "bilibili" / "arxiv"）
  2. 实现 async def fetch_new_urls() -> List[str]
     - 返回该源当前可见的内容 URL 列表
     - 永远不抛业务异常：内部失败应记日志并返回 []（或已抓到的部分）
     - 去重 / 增量判断交给 DBManager.add_new_urls()，源本身只管"发现"
"""

import logging
from abc import ABC, abstractmethod
from typing import List

logger = logging.getLogger(__name__)


class BaseSource(ABC):
    """信息源抽象基类。"""

    #: 源类型唯一标识，子类必须覆盖（如 "bilibili"、"arxiv"）
    source_type: str = "base"

    @abstractmethod
    async def fetch_new_urls(self) -> List[str]:
        """
        发现该源当前可见的内容 URL。

        返回:
            List[str]: URL 列表。可能为空（表示暂无内容或抓取失败）。
                       实现方不应抛出业务异常——失败时记日志并返回 []。
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source_type={self.source_type!r}>"
