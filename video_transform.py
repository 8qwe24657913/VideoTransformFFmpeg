# -*- coding: utf-8 -*-

from __future__ import annotations
# python >= 3.7.0b1 才可使用，python >= 3.10 开始不再需要 import，如果你的 python 版本不够，尝试注释掉该条 import 语句并删除带有 Transform 字样的类型标注或是将其改为字符串 'Transform' 即可让其运行起来

import json
import os
from typing import List, Optional, Union


class Transform(object):
    __slots__ = ['input', 'temp_idx', 'parent',
                 'filter', 'name', 'now_duration']

    def __init__(self, input: str, _parent: Optional[Transform] = None):
        """
        初始化视频/图片变换类

        :param input: 要处理的视频/图片，注意本类中输入的视频/图片路径可能不会被实际确认是否存在
        :param _parent: 内部参数，不需要也不应手动传入
        """
        if _parent is None:
            self.input: List[str] = []
            self.temp_idx = 0
            self.parent = self
        else:
            self.parent = _parent.parent

        self.filter = ''
        self.name: Optional[str] = self.__input(input)
        self.now_duration = None

    def generate_cmd(self, output: str, quiet: bool = True, y: bool = True) -> str:
        """
        生成变换用的命令

        :param output: 输出文件路径
        :param quiet: 静默模式，对应 ffmpeg 的 -v quiet
        :param y: 不进行确认，对应 ffmpeg 的 -y
        :returns: 变换用的命令
        :raises AssertionError
        """
        assert self.parent is self, 'should be called against main branch'
        input = ' '.join(('-i \'{}\''.format(file) for file in self.input))
        duration = '-ss 0 -t {}'.format(
            self.now_duration) if self.now_duration is not None else ''
        if self.filter:
            mapped_video, _ = self.__end()
            filter = '-filter_complex \'{}\' -map [{}] -map 0:a'.format(
                self.filter, mapped_video)
        else:
            filter = ''

        quiet_arg = '-v quiet' if quiet else ''
        y_arg = '-y' if y else ''

        return 'ffmpeg {} {} {} {} {} {}'.format(input, duration, filter, quiet_arg, y_arg, output)

    def run(self, output: str) -> int:
        """
        执行变换

        :param output: 输出文件路径
        :returns: ffmpeg 返回的状态码
        :raises AssertionError
        """
        return os.system(self.generate_cmd(output))

    # 水印/字幕：水印/字幕图像，透明度，位置，大小，角度
    def watermark(self, image: str, alpha: float = 1.0, x: Union[int, str] = 0, y: Union[int, str] = 0, scale: float = 1.0, angle: float = 0.0):
        """
        为视频/图片添加水印/字幕

        :param image: 水印/字幕图像
        :param alpha: 透明度
        :param x: 水平轴上的起始位置
        :param y: 竖直轴上的起始位置
        :param scale: 缩放
        :param angle: 顺时针旋转角度，角度制
        :returns: self
        """
        self.__merge(
            Transform(image, self).scale(scale).rotate(angle).alpha(alpha),
            'overlay={}:{}'.format(x, y)
        )
        return self

    # 加边框：边框比例、位置
    def padding(self, top: Union[int, str] = 0, right: Union[int, str] = 0, bottom: Union[int, str] = 0, left: Union[int, str] = 0):
        """
        为视频/图片添加边框

        :param top: 上方边框宽度
        :param right: 右方边框宽度
        :param bottom: 下方边框宽度
        :param left: 左方边框宽度
        :returns: self
        """
        self.__chain('pad=iw+{}+{}:ih+{}+{}:{}:{}'.format(left,
                                                          right, top, bottom, left, top))
        return self

    # 更改长度：视频的保留比例
    def duration(self, ratio: float = 1.0):
        """
        更改视频时长，注意 ffmpeg 无法精确 seek 到某一帧而只能 seek 到最近的关键帧。此外由于使用时长比例计算，导致该方法会调用 ffprobe 提取视频信息

        :param ratio: 视频的保留比例
        :returns: self
        :raises AssertionError
        """
        assert self.parent is self, 'should be called against main branch'
        if self.now_duration is None:
            cmd = 'ffprobe -v quiet -print_format json -show_format {}'.format(
                self.input[0])
            info = json.loads(os.popen(cmd).read())
            self.now_duration = float(info['format']['duration'])
        self.now_duration *= ratio
        return self

    # 缩放：缩放比例
    def scale(self, ratio: float = 1.0):
        """
        等比例缩放视频/图片

        :param ratio: 缩放比例
        :returns: self
        """
        if ratio != 1.0:
            self.__chain('scale=iw*{}:ih*{}'.format(ratio, ratio))
        return self

    # 镜像
    def mirror(self):
        """
        水平镜像视频/图片

        :returns: self
        """
        self.__chain('hfilp')
        return self

    # 旋转：旋转角度
    def rotate(self, angle: float = 0.0):
        """
        顺时针旋转视频/图片

        :param angle: 顺时针旋转角度，角度制
        :returns: self
        """
        angle %= 360
        if angle == 90:
            self.__chain('transpose=1')
        elif angle == 180:
            self.__chain('transpose=1,transpose=1')
        elif angle == 270:
            self.__chain('transpose=2')
        elif angle != 0:
            radian = '{}*PI/180'.format(angle)
            self.__chain('rotate={}:iw*abs(cos({}))+ih*abs(sin({})):iw*abs(sin({}))+ih*abs(cos({})):fillcolor=none'.format(
                *(radian,)*5))
        return self

    # 亮度：明暗度数
    def brightness(self, brightness: float = 0.0):
        """
        调整视频/图片的亮度

        :param brightness: 亮度
        :returns: self
        """
        self.__chain('eq=brightness={}'.format(brightness))
        return self

    # 剪切：剪切位置、比例
    def crop(self, w: Union[int, str] = 'iw', h: Union[int, str] = 'ih', x: Union[int, str] = 0, y: Union[int, str] = 0):
        """
        裁剪视频/图片

        :param w: 裁剪后的宽度
        :param h: 裁剪后的高度
        :param x: 裁剪水平起始位置
        :param y: 裁剪竖直起始位置
        :returns: self
        """
        self.__chain('crop={}:{}:{}:{}'.format(w, h, x, y))
        return self

    def alpha(self, alpha: float = 1.0):
        """
        调整视频/图片的透明度，目前仅为内部用于调整水印的透明度

        :param alpha: 透明度
        :returns: self
        """
        if alpha != 1.0:
            self.__chain(
                "format=rgba,colorchannelmixer=aa={}".format(alpha))
        return self

    # 以下为内部方法，不做调用方法注释，也不应被手动调用
    def __input(self, input: str):
        self.parent.input.append(input)
        return '{}:v'.format(len(self.parent.input) - 1)

    def __gen_temp(self):
        self.parent.temp_idx += 1
        return "temp{}".format(self.parent.temp_idx)

    def __end(self):
        if self.name:
            return self.name, self.filter
        name = self.__gen_temp()
        self.filter += '[{}]'.format(name)
        return name, self.filter

    def __chain(self, filter: str):
        if self.name:
            self.filter += '[{}]{}'.format(self.name, filter)
            self.name = None
        else:
            self.filter += (',' if self.filter[-1] != ']' else '') + filter

    def __merge(self, another: Transform, merger: str):
        name, _ = self.__end()
        name2, filter2 = another.__end()
        self.filter += ';{};[{}][{}]{}'.format(filter2, name, name2, merger)
        self.name = None


if __name__ == "__main__":
    print(Transform('E:\\short_videoes\\orig\\bad_apple.mp4').duration(
        0.2).scale(2.0).watermark('watermark.png', scale=0.5, alpha=1, angle=45).generate_cmd('wtf.mp4', quiet=False))
