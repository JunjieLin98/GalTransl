# Unity Il2Cpp 场景引导(M5)

## 判定

游戏目录存在 `GameAssembly.dll`(通常在 `<game>_Data/` 或游戏根)+ `il2cpp_data`:
该游戏的 C# 代码已 AOT 编译为原生机器码,脚本/文本若**内嵌在代码中**
(字符串字面量),本套件**不支持**直接提取。

## 什么仍可以做

TextAsset 是**数据层资源**(与代码编译方式无关):Mono 与 Il2Cpp 游戏的
`resources.assets` / `*.bundle` 中的 TextAsset 都可以用本套件 unity profile
正常提取与回封。很多 Unity galgame 把对话文本放在 TextAsset(csv/json/tsv),
这类游戏即使 Il2Cpp 也适用 unity profile。

## 代码内嵌文本 → XUAT 路线

若文本不在 TextAsset 而是硬编码在 C# 程序集(Il2Cpp 场景):

1. **XUAT(IcedSpeller/XUAT 等 Il2Cpp 文本导出工具)**:从 `global-metadata.dat`
   + `GameAssembly.dll` 提取/回封字符串。**本套件不集成、不分发该类工具**,
   由用户自备并自行承担使用责任(与 xp3-brute 同一政策)。
2. 一般流程:用 XUAT 类工具 dump 出文本 → 手工或导入本套件翻译(L4 模式:
   自备 JSON)→ 回封走该工具。
3. 汉化组常见替代:修改 `global-metadata.dat` 的字符串区(需了解格式,风险高,
   务必备份)。

## 本套件的引导行为

- unity profile 检测把 `GameAssembly.dll` 作为引擎特征(hint),检出只影响
  引擎判定,不影响能力等级。
- 翻译中若发现提取产物条目异常稀少,通常是文本不在 TextAsset——此时按上文
  XUAT 路线处理,或确认文本所在文件并在 per-game override 的
  `unpack.archives` 中补齐(如 `*/streamingassets/**/*.bundle`)。
