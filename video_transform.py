# -*- coding: utf-8 -*-

from __future__ import annotations
# python >= 3.7.0b1 才可使用，python >= 3.10 开始不再需要 import，如果你的 python 版本不够，尝试注释掉该条 import 语句并删除带有 Transform 字样的类型标注或是将其改为字符串 'Transform' 即可让其运行起来

import json
import subprocess
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

    def generate_cmd(self, output: str, quiet: bool = True, y: bool = True, accurate_seek: bool = False) -> List[str]:
        """
        生成变换用的命令

        :param output: 输出文件路径
        :param quiet: 静默模式，对应 ffmpeg 的 -v quiet
        :param y: 不进行确认，对应 ffmpeg 的 -y
        :param accurate_seek: 精准时间切割，对应 ffmpeg 的 -accurate_seek -avoid_negative_ts 1
        :returns: 变换用的命令
        :raises AssertionError
        """
        assert self.parent is self, 'should be called against main branch'
        cmd = ['ffmpeg']
        for file in self.input:
            cmd += ['-i', file]
        if self.now_duration is not None:
            cmd += ['-ss', '0', '-t', str(self.now_duration)]
            if accurate_seek:
                cmd += ['-accurate_seek', '-avoid_negative_ts', '1']
        if self.filter:
            mapped_video, _ = self.__end()
            cmd += ['-filter_complex', self.filter, '-map',
                    '[{}]'.format(mapped_video), '-map', '0:a']
        if quiet:
            cmd += ['-v', 'quiet']
        if y:
            cmd += ['-y']
        cmd += [output]

        return cmd

    def run(self, output: str, **kwargs) -> subprocess.CompletedProcess[bytes]:
        """
        执行变换

        :param output: 输出文件路径
        :param **kwargs: 其它 param 参考 generate_cmd()
        :returns: CompletedProcess 对象
        :raises AssertionError
        """
        return subprocess.run(self.generate_cmd(output, **kwargs), check=True, stderr=subprocess.STDOUT)

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
            cmd = ['ffprobe', '-v', 'quiet', '-print_format',
                   'json', '-show_format', self.input[0]]
            info = json.loads(subprocess.run(
                cmd, capture_output=True, check=True).stdout)
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

# 混合：前八种变换方式随机混合


def randomized_transform(inputs: List[str], watermark_images: List[str], outputs: Optional[List[str]] = None):
    """
    将前八种变换方式随机混合

    :param inputs: 输入文件列表
    :param watermark_images: 水印文件列表
    :param outputs: 输出文件列表，若不传则在原文件名后加 '_transformed' 并保存到原目录，若传入则应保证与 inputs 列表长度一致
    :returns: self
    """
    assert outputs is None or len(inputs) == len(
        outputs), 'len(inputs) should be equal to len(outputs)'
    import random
    import os

    def random_watermark(transform: Transform):
        transform.watermark(
            random.choice(watermark_images),
            alpha=random.random(),
            x='{}*(W-w)'.format(random.random()),
            y='{}*(H-h)'.format(random.random()),
            scale=random.random() * 2,
            angle=random.random() * 360
        )

    def random_padding(transform: Transform):
        transform.padding(
            top='{}*ih'.format(random.random() * 0.25),
            right='{}*iw'.format(random.random() * 0.25),
            bottom='{}*ih'.format(random.random() * 0.25),
            left='{}*iw'.format(random.random() * 0.25),
        )

    def random_duration(transform: Transform):
        transform.duration(0.9 + random.random() * 0.1)

    def random_scale(transform: Transform):
        transform.scale(0.4 + random.random() * 0.8)

    def random_rotate(transform: Transform):
        transform.rotate(random.random() * 360)

    def random_brightness(transform: Transform):
        transform.brightness(0.4 + random.random() * 0.8)

    def random_mirror(transform: Transform):
        transform.mirror()

    def random_crop(transform: Transform):
        w = '{}*iw'.format(0.9 + random.random() * 0.1)
        h = '{}*iw'.format(0.9 + random.random() * 0.1)
        transform.crop(
            w=w,
            h=h,
            x='{}*(iw-{})'.format(random.random(), w),
            y='{}*(ih-{})'.format(random.random(), h),
        )

    transform_methods = [
        random_watermark,
        random_padding,
        random_duration,
        random_scale,
        random_rotate,
        random_brightness,
        random_mirror,
        random_crop
    ]
    for i, input in enumerate(inputs):
        transform = Transform(input)
        for method in random.choices(transform_methods, k=random.randint(
                1, len(transform_methods))):
            method(transform)
        transform.run(outputs[i] if outputs is not None else '_transformed'.join(
            os.path.splitext(input)))


if __name__ == "__main__":
    print(Transform(r'E:\short_videoes\orig\bad_apple.mp4').duration(
        0.2).scale(2.0).watermark(r'C:\Users\LiuYuxin\Desktop\watermark.png', scale=0.5, alpha=1, angle=45).run(r'C:\Users\LiuYuxin\Desktop\wtf.mp4', quiet=False))
