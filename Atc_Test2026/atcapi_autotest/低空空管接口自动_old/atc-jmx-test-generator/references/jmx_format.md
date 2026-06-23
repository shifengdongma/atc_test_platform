# JMX 文件格式说明

## 概述

JMX（JMeter XML）是 Apache JMeter 的测试计划文件格式，使用 XML 格式存储测试计划的结构和配置。

## 文件结构

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.4.1">
  <hashTree>
    <!-- TestPlan -->
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="测试计划名称" enabled="true">
      <!-- 用户定义变量 -->
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments">
        <collectionProp name="Arguments.arguments">
          <!-- 变量定义 -->
        </collectionProp>
      </elementProp>
    </TestPlan>
    <hashTree/>
    
    <!-- ThreadGroup -->
    <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="线程组" enabled="true">
      <!-- 线程组配置 -->
    </ThreadGroup>
    <hashTree>
      <!-- 测试元素（HTTP请求、断言、监听器等） -->
    </hashTree>
  </hashTree>
</jmeterTestPlan>
```

## 核心元素

### TestPlan（测试计划）

测试计划的根元素，包含全局配置。

**属性：**
- `guiclass` - GUI 类名（TestPlanGui）
- `testclass` - 测试类名（TestPlan）
- `testname` - 测试计划名称
- `enabled` - 是否启用（true/false）

**子元素：**
- `TestPlan.user_defined_variables` - 用户定义变量
- `TestPlan.comments` - 注释说明

### ThreadGroup（线程组）

定义并发用户配置。

**属性：**
- `guiclass` - ThreadGroupGui
- `testclass` - ThreadGroup
- `testname` - 线程组名称
- `enabled` - 是否启用

**子元素：**
```xml
<stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
<intProp name="ThreadGroup.num_threads">1</intProp>      <!-- 线程数 -->
<intProp name="ThreadGroup.ramp_time">1</intProp>        <!-- 启动时间（秒） -->
<longProp name="ThreadGroup.delay">0</longProp>          <!-- 延迟时间 -->
<longProp name="ThreadGroup.duration">0</longProp>       <!-- 持续时间 -->
<boolProp name="ThreadGroup.scheduler">false</boolProp>  <!-- 是否使用调度器 -->
```

### HTTPSamplerProxy（HTTP 请求）

HTTP 请求采样器。

**属性：**
- `guiclass` - HttpTestSampleGui
- `testclass` - HTTPSamplerProxy
- `testname` - 请求名称
- `enabled` - 是否启用

**子元素：**
```xml
<!-- 服务器配置 -->
<stringProp name="HTTPSampler.domain">${host}</stringProp>
<stringProp name="HTTPSampler.port">${port}</stringProp>
<stringProp name="HTTPSampler.protocol">${protocol}</stringProp>
<stringProp name="HTTPSampler.path">${basePath}/api/endpoint</stringProp>
<stringProp name="HTTPSampler.method">POST</stringProp>

<!-- 编码和超时 -->
<stringProp name="HTTPSampler.contentEncoding">UTF-8</stringProp>
<stringProp name="HTTPSampler.connect_timeout">60000</stringProp>
<stringProp name="HTTPSampler.response_timeout">60000</stringProp>

<!-- 请求体（POST/PUT） -->
<boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
<elementProp name="HTTPsampler.Arguments" elementType="Arguments">
  <collectionProp name="Arguments.arguments">
    <elementProp name="" elementType="HTTPArgument">
      <boolProp name="HTTPArgument.always_encode">false</boolProp>
      <stringProp name="Argument.value">{"key": "value"}</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
    </elementProp>
  </collectionProp>
</elementProp>
```

### HeaderManager（请求头管理器）

管理 HTTP 请求头。

```xml
<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Header Manager" enabled="true">
  <collectionProp name="HeaderManager.headers">
    <elementProp name="Content-Type" elementType="Header">
      <stringProp name="Header.name">Content-Type</stringProp>
      <stringProp name="Header.value">application/json</stringProp>
    </elementProp>
    <elementProp name="jwt-token" elementType="Header">
      <stringProp name="Header.name">jwt-token</stringProp>
      <stringProp name="Header.value">${jwt-token}</stringProp>
    </elementProp>
  </collectionProp>
</HeaderManager>
```

### CookieManager（Cookie 管理器）

管理 HTTP Cookie。

```xml
<CookieManager guiclass="CookiePanel" testclass="CookieManager" testname="Cookie Manager" enabled="true">
  <collectionProp name="CookieManager.cookies"/>
  <boolProp name="CookieManager.clearEachIteration">false</boolProp>
</CookieManager>
```

### TransactionController（事务控制器）

将多个请求组织为一个事务。

```xml
<TransactionController guiclass="TransactionControllerGui" testclass="TransactionController" testname="事务名称" enabled="true">
  <boolProp name="TransactionController.includeTimers">false</boolProp>
  <boolProp name="TransactionController.parent">false</boolProp>
</TransactionController>
```

### JSONPathAssertion（JSON 路径断言）

验证 JSON 响应内容。

```xml
<JSONPathAssertion guiclass="JSONPathAssertionGui" testclass="JSONPathAssertion" testname="断言: status = 200" enabled="true">
  <stringProp name="JSON_PATH">$.status</stringProp>
  <stringProp name="EXPECTED_VALUE">200</stringProp>
  <boolProp name="JSONVALIDATION">true</boolProp>
  <boolProp name="EXPECT_NULL">false</boolProp>
  <boolProp name="INVERT">false</boolProp>
  <boolProp name="ISREGEX">true</boolProp>
</JSONPathAssertion>
```

### JSONPostProcessor（JSON 提取器）

从 JSON 响应中提取数据到变量。

```xml
<JSONPostProcessor guiclass="JSONPostProcessorGui" testclass="JSONPostProcessor" testname="提取: id" enabled="true">
  <stringProp name="JSONPostProcessor.referenceNames">id</stringProp>
  <stringProp name="JSONPostProcessor.jsonPathExprs">$.result.id</stringProp>
  <stringProp name="JSONPostProcessor.defaultValues">NOT_FOUND</stringProp>
  <stringProp name="JSONPostProcessor.match_numbers">1</stringProp>
</JSONPostProcessor>
```

## hashTree 结构说明

`hashTree` 是 JMeter 中用于组织元素层级关系的容器。

### 基本规则

1. **每个元素后面必须跟一个 hashTree**
2. **hashTree 可以包含子元素**
3. **空 hashTree 表示该元素没有子元素**

### 结构示例

```xml
<jmeterTestPlan>
  <hashTree>
    <!-- Level 1: TestPlan -->
    <TestPlan>...</TestPlan>
    <hashTree/>  <!-- TestPlan 的子元素（通常为空） -->
    
    <!-- Level 1: ThreadGroup -->
    <ThreadGroup>...</ThreadGroup>
    <hashTree>
      <!-- Level 2: CookieManager -->
      <CookieManager>...</CookieManager>
      <hashTree/>
      
      <!-- Level 2: HTTP Request -->
      <HTTPSamplerProxy>...</HTTPSamplerProxy>
      <hashTree>
        <!-- Level 3: HeaderManager -->
        <HeaderManager>...</HeaderManager>
        <hashTree/>
        
        <!-- Level 3: Assertion -->
        <JSONPathAssertion>...</JSONPathAssertion>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
```

## 变量引用

### 用户定义变量

```xml
<elementProp name="TestPlan.user_defined_variables" elementType="Arguments">
  <collectionProp name="Arguments.arguments">
    <elementProp name="host" elementType="Argument">
      <stringProp name="Argument.name">host</stringProp>
      <stringProp name="Argument.value">dkkgsit-test.testdolphin.com</stringProp>
      <stringProp name="Argument.metadata">=</stringProp>
    </elementProp>
  </collectionProp>
</elementProp>
```

### 变量引用语法

```xml
<!-- 基本变量引用 -->
<stringProp name="HTTPSampler.domain">${host}</stringProp>

<!-- 带默认值的变量引用 -->
<stringProp name="Argument.value">${__P(host,dkkgsit-test.testdolphin.com)}</stringProp>

<!-- JMeter 函数 -->
<stringProp name="Argument.value">${__time(MMddHHmmss)}</stringProp>
<stringProp name="Argument.value">${__RandomString(10,abcdefghijklmnopqrstuvwxyz,)}</stringProp>
```

## 常见错误

### ClassCastException

**错误信息：**
```
ClassCastException: org.apache.jmeter.threads.ThreadGroup cannot be cast to org.apache.jorphan.collections.HashTree
```

**原因：** ThreadGroup 没有正确放置在 hashTree 下。

**解决：** 确保 ThreadGroup 和 TestPlan 都在根 hashTree 下，且每个元素后面都有对应的 hashTree。

### 变量未定义

**错误信息：**
```
Undefined variable: host
```

**原因：** 使用了未定义的变量。

**解决：** 在 TestPlan 的 User Defined Variables 中定义变量，或使用 `${__P(var,default)}` 提供默认值。
