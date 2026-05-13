请重构当前项目，遵循以下步骤与要求规范。

## 项目状态描述：
- 当前项目已经进行了部分的重构。当前webui下的app.py已经经过了部分的修改，部分代码已被移除且暂时无法使用。访问旧版app.py，请访问app_discard.py。
- 当前项目中，已经完成了部分新版本的基础设施，详情可见globalManagers目录。然而，大部分的脚本任然使用了旧版基础设施。对于原先的文件，需要将其的配置相关逻辑修改至configManager，路径获取修改至pathManager
- 当前的项目结构为从start_webui.py路由至webui\app.py，随后启动webui。webui通过webui\app.py中提供的LCTA_API类进行映射，同时前端使用webui\index.html，webui\script.js，webui\style.css三个文件进行显示。

## 规范与要求：
- 使用globalManagers目录下的新基础设施重构所有的脚本，注意，无需做出向下兼容操作，所有的旧版本逻辑需要完全修改为新版本的类。
- 新版本的项目结构需要做出大规模的重构。新版本的项目结构概述如下:
  通过start_webui.py路由启动，路由至webui\webuiHandel.py，项目本体仅携带基础设施，将不同页面插件化管理，加载时从指定文件夹处理所有插件，通过api和配置文件管理加载时机，需要提前加载的脚本和注册的配置项。web页面中只在需要时加载对应页面的html，js和python脚本(可通过配置文件自定义加载时机)。
- - 完全修改app.py，将app.py作为一个api函数提供类。提供例如配置项注册，函数注册等辅助装饰器模组。webui\webuiHandel.py将代替原先app.py的启动托盘的生态位。

## 额外的要求：
除了上述提到的重构要求之外，你还需要完成以下操作：

- 重构translateFunc，修复其中的已有问题，同时修改函数结构，使用更加pythonic，可读，易于调试与记录的方式进行重构。
- 修改globalManagers\configManager.py，将其与前端页面的configManager进行同步，使得通过尽量简洁，请求数量少的方式进行配置项同步。
- 重构launcher\main.py，使其更加易于维护。
- 重构美化相关函数，使得built-in加载更加符合层次设计。
- 修改webutils\function_llc.py和webutils\function_ourplay.py的函数设计，增强代码复用。
- 删除旧版的基础设施
- 优化函数与代码的设计，使其更加pythonic
- 优化日志逻辑，使得通过日志排查错误更加方便。

对于这些额外的要求，在做计划时需要为每一个需求起一个章节来详细描述你对实现这些要求的计划。

## 顺序
对当前项目结构进行重构，采用规范与要求章节的描述对整个项目进行重构。在重构完成前，无需处理额外的要求