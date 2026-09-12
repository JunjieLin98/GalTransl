"""错误码目录:每码 = 机器码 + 人话解释 + 可行动指引(需求 FR-G3)。"""

from __future__ import annotations

GUIDANCE: dict[str, str] = {
    "E-DETECT-UNKNOWN-ENGINE": (
        "未能识别游戏引擎。"
        "处理:①用 --profile 手动指定引擎;②若为长尾引擎,可按 SExtractor 正则方式人工编写提取配置;"
        "③带本目录文件清单到项目 issue 反馈引擎适配请求。"
    ),
    "E-UNPACK-ENCRYPTED-XP3": (
        "封包已加密且自动解密失败(解包工具无产物,或回退解密工具不可用)。"
        "处理:①自备 xp3brute.exe(解密工具,本项目不分发)放入 tools/bin/(或用 --tools-dir/GUI 工具目录指定)后重跑 UNPACK,"
        "将在工作目录找到该工具时自动回退解密;"
        "②或用解密工具手动解包,将解出文件放入 work/unpacked/<封包名>/ 后从 EXTRACT 步骤继续重跑;"
        "③解密工具的使用责任由用户自行承担。"
    ),
    "E-UNPACK-NO-ARCHIVE": (
        "游戏目录中未找到匹配 unpack.archives 的封包。"
        "处理:①确认 game_dir 指向游戏根目录;"
        "②用 per-game override 增加/调整 unpack.archives 模式(如 'pac/*.xp3');"
        "③若游戏为已解包目录形态,跳过 UNPACK 从 EXTRACT 重跑。"
    ),
    "E-EXTRACT-NO-SCRIPT": (
        "解包产物中未找到可提取的脚本文件。"
        "处理:检查 profile 的 extract.input_glob 是否匹配该游戏(可用 per-game override 调整);"
        "或确认解包目录是否正确。"
    ),
    "E-EXTRACT-TOOL-MISSING": (
        "外部工具缺失或校验失败。"
        "处理:将工具放入 tools/bin/(msg_tool.exe / Xp3Pack.exe 等),"
        "或用 --tools-dir 指定工具目录;工具获取方式见 docs/architecture.md §6 工具托管表。"
    ),
    "E-TOOL-PROCESS-CRASH": (
        "外部工具异常退出或超时。"
        "处理:①查看附带的标准输出/标准错误尾部;②确认杀毒软件未拦截;③单独重跑该步骤。"
    ),
    "E-TRANSLATE-API-AUTH": (
        "翻译 API 鉴权失败或未配置。"
        "处理:①在工程 config.yaml 的 backendSpecific.OpenAI-Compatible.tokens 中填写有效的 API key;"
        "②或用 --api-key/--endpoint/--model 参数注入;③用 galtrans run --from-step TRANSLATE 重跑。"
    ),
    "E-TRANSLATE-OUTPUT-MISSING": (
        "翻译完成后输出文件数量与输入不一致。"
        "处理:检查翻译日志(backend 返回的失败批次会标记 (Failed));修复后重跑 TRANSLATE(缓存兜底,只补失败句)。"
    ),
    "E-INJECT-IMPORT-FAIL": (
        "译文导入回填失败。"
        "处理:①若为编码缺字,切换 constraints.encoding_mode(gbk/sjis);"
        "②若为译文超长,缩短对应句译文后重试;③保留 L3 产物(译文 JSON)可人工回填。"
    ),
    "E-PACKAGE-FONT-MISSING": (
        "检测到游戏默认字体可能缺少中文字形。"
        "处理:替换游戏字体为中文(如「思源黑体」),或将中文字体放入补丁并修改启动脚本字体配置;"
        "详见安装说明中的字体替换章节。"
    ),
    "E-PACKAGE-ANTIVIRUS": (
        "补丁中的 version.dll 可能被杀毒软件拦截。"
        "处理:该 DLL 来自 KirikiriTools(免封包加载组件),属误报常见对象;"
        "将游戏目录加入杀软白名单后重新放置补丁。"
    ),
    "E-PROJECT-GAME-MISSING": (
        "工程记录的游戏目录不存在。"
        "处理:编辑 project.yaml 中 game_dir 重新指向游戏目录;workspace 内相对路径产物不受影响。"
    ),
    "E-CACHE-BUSY": (
        "翻译任务正在进行,缓存暂不可写。"
        "处理:等待翻译完成或取消任务后再编辑译文。"
    ),
    "E-CACHE-EDIT-INVALID": (
        "缓存编辑写回被拒绝(定位失败/锁定空译文/缓存文件异常)。"
        "处理:刷新编辑器重新加载缓存;锁定条目必须已有译文;"
        "若缓存被重新生成,以最新数据为准重新编辑。"
    ),
    "E-RESTORE-NO-BACKUP": (
        "没有可用的备份可供恢复。"
        "处理:确认 backup/ 目录存在且非空;restore 仅在执行过写回类步骤后可用。"
    ),
    "E-UNITY-FORMAT": (
        "Unity TextAsset 的内容不是受支持的格式(当前支持 JSON 数组 [{name,message}] 或 TSV)。"
        "处理:确认该 TextAsset 是否为对话文本;其他格式(纯文本/自定义结构)暂不支持,"
        "可在 per-game override 中排除该文件或用 L4 模式自备 JSON 翻译。"
    ),
    "E-UNITY-DEPLOY-AMBIGUOUS": (
        "部署时在游戏目录找到 0 个或多个同名文件,无法唯一定位。"
        "处理:在 per-game override 的 unpack.archives 中写完整相对路径(相对游戏根),"
        "并确保没有同名文件散布在多个目录。"
    ),
    "E-INVALID-PROFILE": (
        "引擎 profile 配置无效。"
        "处理:检查 profiles/ 下 YAML 的必填字段(profile/capability/steps);参考 kirikiri.yaml 结构。"
    ),
}


class PipelineError(Exception):
    """带错误码与可行动指引的流水线异常。"""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.guidance = GUIDANCE.get(code, "")
        detail = f"{code}: {message}" if message else code
        if self.guidance:
            detail = f"{detail}\n指引: {self.guidance}"
        super().__init__(detail)
