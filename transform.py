# -*- coding: utf-8 -*-

from __future__ import annotations
# python >= 3.7.0b1 才可使用，python >= 3.10 开始不再需要 import，如果你的 python 版本不够，尝试注释掉该条 import 语句并删除带有 Transform 字样的类型标注或是将其改为字符串 'Transform' 即可让其运行起来

import random
import subprocess
from typing import (Callable, Dict, List, Optional, Sequence, Tuple, TypeVar,
                    Union)
import ffmpeg
import math

# ffmpeg 表达式
Expression = Union[int, float, str]
# 文件的路径
FilePath = str
# 文件的参数及路径
FileParameters = Dict[str, Optional[str]]
# 文件描述
FileDesc = Union[FilePath, FileParameters]
# 方法的参数
Argument = Union[Expression, FilePath]
# 为参数指定一个列表，意为在列表中随机选择一个
ArgumentList = Sequence[Argument]
# 参数名
ArgumentName = str
# 一组参数，参数名与参数的对应关系
Arguments = Dict[ArgumentName, Union[Argument,
                                     ArgumentList, Callable[[], Argument]]]
# 为一组参数指定一个列表，意为在列表中随机选择一组
ArgumentsList = Sequence[Arguments]
# 方法名
MethodName = str
# 方法与参数的对应关系
ArgumentsForMethod = Dict[MethodName, Union[Arguments,
                                            ArgumentsList, Callable[[], Arguments]]]


T = TypeVar('T')
# 单个值、从序列中随机选一个值、使用自定义函数手动选取一个值
Chooseable = Union[T, Sequence[T], Callable[[], T]]


def choice(arg: Chooseable[T]) -> T:
    if isinstance(arg, Sequence) and not isinstance(arg, str):
        return random.choice(arg)
    elif callable(arg):
        return arg()
    else:
        return arg


class Transform(object):
    __slots__ = ['input', 'stream', 'now_duration']

    def __init__(self, input: FileDesc):
        """
        初始化视频/图片变换类

        :param input: 要处理的视频/图片，注意本类中输入的视频/图片路径可能不会被实际确认是否存在
        :param _parent: 内部参数，不需要也不应手动传入
        """
        self.input = self.__get_file_parameters(input)
        self.stream: ffmpeg.Stream = self.__input(self.input)
        self.now_duration: Optional[Tuple[float, float]] = None

    def generate_cmd(self, output: FileDesc, quiet: bool = True, y: bool = True, accurate_seek: bool = False, other_args: List[str] = []) -> List[str]:
        """
        生成变换用的命令

        :param output: 输出文件
        :param quiet: 静默模式，对应 ffmpeg 的 -v quiet
        :param y: 不进行确认，对应 ffmpeg 的 -y
        :param accurate_seek: 精准时间切割，对应 ffmpeg 的 -accurate_seek -avoid_negative_ts 1
        :param other_args: 其它 ffmpeg 的参数
        :returns: 变换用的命令
        :raises AssertionError
        """

        global_args = []
        if self.now_duration is not None:
            self.input.update({
                'ss': str(self.now_duration[0]),
                't': str(self.now_duration[1]),
            })
            if accurate_seek:
                self.input.update({
                    'accurate_seek': None,
                    'avoid_negative_ts': '1',
                })
        if quiet:
            global_args += ['-v', 'quiet']
        global_args += other_args
        stream = ffmpeg.output(
            self.stream,
            **self.__get_file_parameters(output),
        )
        if global_args:
            stream = ffmpeg.nodes.GlobalNode(
                stream,
                'my_args',
                global_args
            ).stream()

        return ffmpeg.compile(stream, overwrite_output=y)

    def run(self, output: FileDesc, **kwargs) -> subprocess.CompletedProcess[bytes]:
        """
        执行变换

        :param output: 输出文件
        :param **kwargs: 其它 param 参考 generate_cmd()
        :returns: CompletedProcess 对象
        :raises AssertionError
        """
        return subprocess.run(self.generate_cmd(output, **kwargs), check=True, stderr=subprocess.STDOUT)

    # 水印/字幕：水印/字幕图像，透明度，位置，大小，角度
    def watermark(self, image: FileDesc, alpha: float = 1.0, x: Expression = 0, y: Expression = 0, scale: float = 1.0, angle: float = 0.0):
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
        self.stream = ffmpeg.overlay(
            self.stream,
            Transform(image).scale(scale).rotate(angle).alpha(alpha).stream,
            x=x,
            y=y,
        )
        return self

    # 加边框：边框比例、位置
    def padding(self, top: Expression = 0, right: Expression = 0, bottom: Expression = 0, left: Expression = 0):
        """
        为视频/图片添加边框

        :param top: 上方边框宽度
        :param right: 右方边框宽度
        :param bottom: 下方边框宽度
        :param left: 左方边框宽度
        :returns: self
        """
        # http://trac.ffmpeg.org/ticket/1618
        self.filter(
            'pad',
            'ceil((iw+x+{})/2)*2'.format(right),
            'ceil((ih+y+{})/2)*2'.format(bottom),
            'round({})'.format(left),
            'round({})'.format(top),
        )
        return self

    # 更改长度：视频的保留比例
    def duration(self, start_ratio: float = 0.0, ratio: float = 1.0, duration=None):
        """
        更改视频时长，注意 ffmpeg 无法精确 seek 到某一帧而只能 seek 到最近的关键帧。此外由于使用时长比例计算，导致该方法会调用 ffprobe 提取视频信息

        :param start_ratio: 视频开始的比例
        :param ratio: 视频的保留比例
        :param duration: 视频的长度，用于避免通过 ffprobe 获取长度
        :returns: self
        :raises AssertionError
        """
        assert start_ratio + ratio <= 1.0, 'should not longer than original video'
        if self.now_duration is None:
            if duration is None:
                filename = self.input['filename']
                duration = ffmpeg.probe(filename)['format']['duration']
            self.now_duration = (0.0, float(duration))
        start, end = self.now_duration
        length = end - start
        start += length * start_ratio
        end = start + length * ratio
        self.now_duration = (start, end)
        return self

    # 缩放：缩放比例
    def scale(self, ratio: float = 1.0):
        """
        等比例缩放视频/图片

        :param ratio: 缩放比例
        :returns: self
        """
        if ratio != 1.0:
            # 为什么只能是偶数？
            self.filter(
                'scale',
                'round(iw*{}/2)*2'.format(ratio),
                'round(ih*{}/2)*2'.format(ratio),
            )
        return self

    # 镜像
    def mirror(self):
        """
        水平镜像视频/图片

        :returns: self
        """
        self.filter('hflip')
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
            self.filter('transpose', '1')
        elif angle == 180:
            self.filter('transpose', '1').filter('transpose', '1')
        elif angle == 270:
            self.filter('transpose', '2')
        elif angle != 0:
            radian = math.radians(angle)
            abssin = abs(math.sin(radian))
            abscos = abs(math.cos(radian))
            radian = '{}*PI/180'.format(angle)
            self.filter(
                'rotate',
                radian,
                'iw*{}+ih*{}'.format(abscos, abssin),
                'iw*{}+ih*{}'.format(abssin, abscos),
                fillcolor='none',
            )
        return self

    # 亮度：明暗度数
    def brightness(self, brightness: float = 0.0):
        """
        调整视频/图片的亮度

        :param brightness: 亮度
        :returns: self
        """
        self.filter('eq', brightness=brightness)
        return self

    # 剪切：剪切位置、比例
    def crop(self, w: Expression = 'iw', h: Expression = 'ih', x: Expression = 0, y: Expression = 0):
        """
        裁剪视频/图片

        :param w: 裁剪后的宽度
        :param h: 裁剪后的高度
        :param x: 裁剪水平起始位置
        :param y: 裁剪竖直起始位置
        :returns: self
        """
        self.filter(
            'crop',
            w=w,
            h=h,
            x=x,
            y=y,
        )
        return self

    def alpha(self, alpha: float = 1.0):
        """
        调整视频/图片的透明度，目前仅为内部用于调整水印的透明度

        :param alpha: 透明度
        :returns: self
        """
        self.filter('format', 'rgba').filter('colorchannelmixer', aa=alpha)
        return self

    def filter(self, *args, **kwargs):
        self.stream = ffmpeg.filter(self.stream, *args, **kwargs)
        return self

    methods: Sequence[MethodName] = (
        'watermark',
        'padding',
        'duration',
        'scale',
        'rotate',
        'brightness',
        'mirror',
        'crop',
    )

    # 混合：前八种变换方式随机混合
    def mixed(
        self,
        args: ArgumentsForMethod = {},
        methods: Sequence[MethodName] = methods,
        k: Optional[Chooseable[int]] = None,
    ):
        """
        将前八种变换方式随机混合

        :param args: 传入各函数的参数或参数取值的可选列表，以 watermark 方法为例：
            固定单组参数：
            {
                'watermark': {
                    'image': '1.png',
                    'alpha': 0.5,
                }
            }
            对于单个参数的随机：
            {
                'watermark': {
                    'image': ['1.png', '2.png'],
                    'alpha': 0.5,
                }
            }
            对于参数组的随机：
            {
                'watermark': [
                    {
                        'image': ['1.png', '2.png'],
                        'alpha': 0.5,
                    }, {
                        'image': '3.png',
                        'alpha': 0.8,
                    }
                ]
            }
            自定义随机：
            {
                'watermark': lambda: random.choices([
                    {
                        'image': '1.png',
                        'alpha': lambda: random.random() * 0.8 + 0.2,
                    }, {
                        'image': '2.png',
                        'alpha': lambda: random.random() * 0.7 + 0.3,
                    }
                ], weights=[2, 3])[0]
            }
        :param methods: 要使用的变换列表，默认为全部八种变换
        :param k: 对每个应用几种变换
        :returns: self
        """
        if k is None:
            def random_k(): return random.randint(1, len(methods))
            k = random_k
        for method in random.sample(methods, k=choice(k)):
            kwargs = {
                name: choice(argument) for name, argument in choice(args.get(method, {})).items()
            }
            getattr(self, method)(**kwargs)
        return self

    # 以下为内部方法，不做调用方法注释，也不应被手动调用

    @staticmethod
    def __get_file_parameters(file: FileDesc) -> FileParameters:
        return file if isinstance(file, dict) else {
            'filename': file,
        }

    def __input(self, input: FileDesc) -> ffmpeg.Stream:
        return ffmpeg.input(**self.__get_file_parameters(input))


# 默认参数为随机的 Transform 类
# 用户也可以通过像这样继承 Transform 类来对方法进行扩展从而达到更高的自由度，比如增加一种变换方式
class RandomizedTransform(Transform):
    def __super(self):
        return super(RandomizedTransform, self)

    def watermark(
        self,
        image: str,
        alpha: Optional[float] = None,
        x: Optional[Expression] = None,
        y: Optional[Expression] = None,
        scale: Optional[float] = None,
        angle: Optional[float] = None,
    ):
        if alpha is None:
            alpha = 0.3 + random.random() * 0.7
        if x is None:
            x = '{}*(W-w)'.format(random.random())
        if y is None:
            y = '{}*(H-h)'.format(random.random())
        if scale is None:
            scale = random.random() * 2
        if angle is None:
            angle = random.random() * 360
        self.__super().watermark(image, alpha, x, y, scale, angle)
        return self

    def padding(
        self,
        top: Optional[Expression] = None,
        right: Optional[Expression] = None,
        bottom: Optional[Expression] = None,
        left: Optional[Expression] = None,
    ):
        if top is None:
            top = '{}*ih'.format(random.random() * 0.25)
        if right is None:
            right = '{}*iw'.format(random.random() * 0.25)
        if bottom is None:
            bottom = '{}*ih'.format(random.random() * 0.25)
        if left is None:
            left = '{}*iw'.format(random.random() * 0.25)
        self.__super().padding(top, right, bottom, left)
        return self

    def duration(
        self,
        start_ratio: Optional[float] = None,
        ratio: Optional[float] = None,
    ):
        if start_ratio is None:
            start_ratio = random.random() * 0.1 * (1.0 - (ratio or 0.0))
        if ratio is None:
            ratio = (0.9 + random.random() * 0.1) * (1.0 - start_ratio)
        self.__super().duration(start_ratio, ratio)
        return self

    def scale(
        self,
        ratio: Optional[float] = None,
    ):
        if ratio is None:
            ratio = 0.4 + random.random() * 0.8
        self.__super().scale(ratio)
        return self

    def rotate(
        self,
        angle: Optional[float] = None,
    ):
        if angle is None:
            angle = random.randint(0, 3) * 90.0
        self.__super().rotate(angle)
        return self

    def brightness(
        self,
        brightness: Optional[float] = None,
    ):
        if brightness is None:
            brightness = 0.4 * random.random() - 0.2
        self.__super().brightness(brightness)
        return self

    def crop(
        self,
        w: Optional[Expression] = None,
        h: Optional[Expression] = None,
        x: Optional[Expression] = None,
        y: Optional[Expression] = None,
    ):
        if w is None:
            w = '{}*iw'.format(0.9 + random.random() * 0.1)
        if h is None:
            h = '{}*ih'.format(0.9 + random.random() * 0.1)
        if x is None:
            x = '{}*(iw-ow)'.format(random.random(), w)
        if y is None:
            y = '{}*(ih-oh)'.format(random.random(), h)
        self.__super().crop(w, h, x, y)
        return self


__all__ = ('Transform', 'RandomizedTransform')
