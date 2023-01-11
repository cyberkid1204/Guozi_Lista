# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author     ：NanZhou
# version    ：python 3.9.7
# =============================================
from __future__ import annotations
import os.path
from typing import List, Dict
from abc import ABC, abstractmethod


# Remote service interface
class ThirdPartyLib(ABC):
    @abstractmethod
    def list_videos(self):
        pass

    @abstractmethod
    def get_video_info(self):
        pass

    @abstractmethod
    def download_video(self):
        pass


# Tencent services
class ThirdPartyTVClass(ThirdPartyLib):
    def list_videos(self):
        # send an api request to tencent video
        videos = ["Fast & Furious 1",
                  "Fast & Furious 2",
                  "Fast & Furious 3",
                  "Fast & Furious 4"]
        return videos

    def get_video_info(self):
        # fetching video datas
        video_details = {
            1: {"name": "Fast & Furious 1", "score": 9.5, "date": "2008-08"},
            2: {"name": "Fast & Furious 2", "score": 8.8, "date": "2010-10"},
            3: {"name": "Fast & Furious 3", "score": 9.1, "date": "2012-05"},
            4: {"name": "Fast & Furious 4", "score": 9.3, "date": "2013-08"},
        }
        return video_details

    def download_video(self):
        # For download the video file
        video_details = dict()
        return video_details


# Proxy server
class CachedTVClass(ThirdPartyLib):
    def __init__(self, service: ThirdPartyTVClass()) -> None:
        self._service = service
        self._list_cache = list()
        self._video_cache = dict()
        self._video_download = dict()
        self._need_request = self.need_request()

    def need_request(self) -> bool:
        return False if self._list_cache and self._video_cache else True

    def list_videos(self) -> List[str]:
        if not self._list_cache or self._need_request:
            video_data = self._service.list_videos()
            for ele in video_data:
                self._list_cache.append(ele)
        return self._list_cache

    def get_video_info(self) -> Dict[int:Dict[str, str]]:
        if not self._video_cache or self._need_request:
            video_info = self._service.get_video_info()
            for video_id, details in video_info.items():
                if not (video_id in self._video_cache):
                    self._video_cache[video_id] = details
        return self._video_cache

    def download_video(self) -> Dict[int, str]:
        default_download_path = str(os.path.dirname(os.getcwd())) + "\\download"
        for vid, _ in self._video_cache.items():
            if vid not in self._video_download:
                self._video_download[vid] = default_download_path
        return self._video_download


class User:
    def __init__(self, proxy: CachedTVClass(ThirdPartyTVClass())) -> None:
        self.proxy = proxy

    def show_movie_list(self) -> None:
        print("当下热映".center(50, "-"))
        for ele in self.proxy.list_videos():
            print(f"片名：{ele}")

    def show_movie_info(self) -> None:
        print(self.proxy.get_video_info())

    def show_download_movie(self) -> None:
        print(self.proxy.download_video())

    def show(self) -> None:
        print("当下热映".center(50, "-"))
        for _, movie in self.proxy.get_video_info().items():
            print(f"片名：{movie['name']}\t评分：{movie['score']}\t上映日期：{movie['date']}")


if __name__ == '__main__':
    Adrian = User(CachedTVClass(ThirdPartyTVClass()))
    # Adrian.show_movie_list()
    Adrian.show()
    # Adrian.show_movie_info()
    Adrian.show_download_movie()
