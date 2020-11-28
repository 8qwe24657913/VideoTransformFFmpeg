# -*- coding: utf-8 -*-

from __future__ import annotations
# python >= 3.7.0b1 才可使用，python >= 3.10 开始不再需要 import，如果你的 python 版本不够，尝试注释掉该条 import 语句并删除带有 Transform 字样的类型标注或是将其改为字符串 'Transform' 即可让其运行起来

import os
import random
import subprocess
from typing import Callable, Dict, List, Optional, Sequence, TypeVar, Union

# ffmpeg 表达式
Expression = Union[int, float, str]
# 文件的路径
FilePath = str
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
    if isinstance(arg, Sequence):
        return random.choice(arg)
    elif callable(arg):
        return arg()
    else:
        return arg


class Transform(object):
    __slots__ = ['input', 'temp_idx', 'parent',
                 'filter', 'name', 'now_duration']

    def __init__(self, input: FilePath, _parent: Optional[Transform] = None):
        """
        初始化视频/图片变换类

        :param input: 要处理的视频/图片，注意本类中输入的视频/图片路径可能不会被实际确认是否存在
        :param _parent: 内部参数，不需要也不应手动传入
        """
        if _parent is None:
            self.input: List[FilePath] = []
            self.temp_idx = 0
            self.parent = self
        else:
            self.parent = _parent.parent

        self.filter = ''
        self.name: Optional[str] = self.__input(input)
        self.now_duration = None

    def generate_cmd(self, output: FilePath, quiet: bool = True, y: bool = True, accurate_seek: bool = False) -> List[str]:
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
            cmd += ['-filter_complex', self.filter]
        if quiet:
            cmd += ['-v', 'quiet']
        if y:
            cmd += ['-y']
        cmd += [output]

        return cmd

    def run(self, output: FilePath, **kwargs) -> subprocess.CompletedProcess[bytes]:
        """
        执行变换

        :param output: 输出文件路径
        :param **kwargs: 其它 param 参考 generate_cmd()
        :returns: CompletedProcess 对象
        :raises AssertionError
        """
        return subprocess.run(self.generate_cmd(output, **kwargs), check=True, stderr=subprocess.STDOUT)

    # 水印/字幕：水印/字幕图像，透明度，位置，大小，角度
    def watermark(self, image: FilePath, alpha: float = 1.0, x: Expression = 0, y: Expression = 0, scale: float = 1.0, angle: float = 0.0):
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
    def padding(self, top: Expression = 0, right: Expression = 0, bottom: Expression = 0, left: Expression = 0):
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
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                   '-of', 'default=noprint_wrappers=1:nokey=1', self.input[0]]
            duration = subprocess.run(
                cmd, capture_output=True, check=True).stdout
            assert duration != 'N/A', 'duration info not available'
            self.now_duration = float(duration)
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
    def crop(self, w: Expression = 'iw', h: Expression = 'ih', x: Expression = 0, y: Expression = 0):
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
    @classmethod
    def mixed(
        cls,
        inputs: Sequence[FilePath],
        args: ArgumentsForMethod = {},
        methods: Sequence[MethodName] = methods,
        k: Optional[Chooseable[int]] = None,
        assign_output: Callable[[FilePath], FilePath] = lambda input: '_transformed'.join(os.path.splitext(input)),
    ):
        """
        将前八种变换方式随机混合

        :param inputs: 输入文件列表
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
        :param assign_output: 为每个输入文件指定一个输出文件，默认为在原文件名后加 '_transformed' 并保存到原目录
        :returns: self
        """
        def random_k(): return random.randint(1, len(methods))
        if k is None:
            k = random_k
        for input in inputs:
            transform = cls(input)
            for method in random.sample(methods, k=choice(k)):
                kwargs = {
                    name: choice(argument) for name, argument in choice(args.get(method, default={})).items()
                }
                getattr(cls, method)(transform, **kwargs)
            transform.run(assign_output(input))

    # 以下为内部方法，不做调用方法注释，也不应被手动调用
    def __input(self, input: FilePath):
        self.parent.input.append(input)
        return str(len(self.parent.input) - 1)

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
            alpha = random.random()
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
        ratio: Optional[float] = None,
    ):
        if ratio is None:
            ratio = 0.9 + random.random() * 0.1
        self.__super().duration(ratio)
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
            angle = random.random() * 360
        self.__super().rotate(angle)
        return self

    def brightness(
        self,
        brightness: Optional[float] = None,
    ):
        if brightness is None:
            brightness = 0.4 + random.random() * 0.8
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
            x = '{}*(iw-{})'.format(random.random(), w)
        if y is None:
            y = '{}*(ih-{})'.format(random.random(), h)
        self.__super().crop(w, h, x, y)
        return self
