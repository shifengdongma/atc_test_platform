创建飞行任务角色：
    超管：atcAdmin
    组织机构：单位操作员
# 基础信息
"taskName":"飞行任务060201","taskPurpose":"13","taskType":"SINGLE","operatorType":"2","operatorId":"1","operatorName":"atcAdmin","uavType":"MICRO","flightMode":"0","flightControlMode":"2","contact":"atcAdmin","phoneNumber":"13812345661","files":[],"isDangerousGoods":false,"isMovingOper":false,"isOverCrowds":false,"isRtOrSwarm":false,"isRelayOrNet":false,"taskDesc":""
1.任务名称 taskName：自定义，不超过50个字符
2.任务性质 taskPurpose ：数据库中，表：code_item，ID 104~136，取值：CODE_ITEM_VALUE，UI上展示：CODE_ITEM_NAME
3.任务类别 taskType ：数据库中，表：code_item，ID 137~139，取值：CODE_ITEM_VALUE ，UI上展示：CODE_ITEM_NAME
    任务性质和任务类别关联：
        城市空中消防、空中医疗紧急救援、森林防火与护林：任务类别可以选择：单次、多次、应急
        其余的任务性质，任务类别只能选择：单次、多次
4.运营人类型 operatorType：组织机构：2，个人 1
    个人：使用当前登录用户信息，填充运营人信息 operatorName、联系人contact:当前登录个人信息、联系方式phoneNumber：当前登录个人联系方式：
        个人：数据库中表：operation_people  
    组织机构：当前登录用户所在单位信息，运营人信息operatorName：单位管理员信息，联系方式phoneNumber:单位管理员信息联系方式
        组织机构信息：数据库中表：operation_organization 
5.飞行模式 flightMode：超视距飞行 0；视距内飞行 1
6.操控模式 flightControlMode：遥控飞行： 自主飞行：2

## 涉及活动申报
1.运载危险品或投放物品（农用无人机作业除外）isDangerousGoods：false true ；飞跃集会人群上空 isMovingOper：：false true ；在移动交通工具上操控航空器 isOverCrowds ：false true ；实时分布式或集群飞行 isRtOrSwarm：false true ；通过通信基站或互联网实现中继飞行 isRelayOrNet：false true 
2.飞行事由 taskDesc：200以内文字描述

# 执行信息
,"periods":[{"startTime":1780392238857,"endTime":1780415999000}],"uavInfos":[{"uavId":"50510186246356992","uavName":"智能巡航无人机7号","uavIdentifyCode":"ZT000000000000000007","policyNumber":"4007093556","insuranceCompany":"中华联合","registrationCode":"EHH0000000007","manufacturer":"科卫泰","uavType":"MICRO","uavModel":"DT-EVO"}],"pilots":[{"operatorId":"40633100413255680","operatorName":"wwbcz","idType":"0","operatorIdNumber":"410825199407258824","rplType":"RPL_M","licenseNumber":"HK202604220030021","operatorLicenseValidity":1848499200000}],
## 任务时间段
单次：起始时间 延迟3分钟，结束时间：起始时间延迟30分钟，可以配置
多次：
## 执行周期
不重复
## 航空器信息
1.从数据库表：uav_info ，查询某个航空器需要的字段，最好个人查询个人名下的，单位查询组织机构下的航空器
## 操作员信息
1.从数据库表：operation_people，查询自己所在组织架构下的操作员信息，或者随机查询一个操作员信息

# 航线选择的，待补充
先使用默认的
"observers":[],"repeatConfig":{},"flightLines":[{"lineSegments":[{"type":2,"airRouteId":"23560499761315840","airRouteElementId":"50734005686992896","startPointLon":120.687215,"startPointLat":31.33317,"startPointHeight":60,"endPointLon":120.70385,"endPointLat":31.334298,"endPointHeight":60,"width":200,"protectHeight":500,"airRouteSegmentSeq":1},{"type":2,"airRouteId":"23560499761315840","airRouteElementId":"50734005691187200","startPointLon":120.70385,"startPointLat":31.334298,"startPointHeight":60,"endPointLon":120.719165,"endPointLat":31.337681,"endPointHeight":60,"width":200,"protectHeight":500,"airRouteSegmentSeq":2},{"type":2,"airRouteId":"23560499761315840","airRouteElementId":"50734005691187201","startPointLon":120.719165,"startPointLat":31.337681,"startPointHeight":60,"endPointLon":120.736724,"endPointLat":31.337906,"endPointHeight":60,"width":200,"protectHeight":500,"airRouteSegmentSeq":3},{"type":2,"airRouteId":"23560499761315840","airRouteElementId":"50734005691187202","startPointLon":120.736724,"startPointLat":31.337906,"startPointHeight":60,"endPointLon":120.741081,"endPointLat":31.333734,"endPointHeight":60,"width":200,"protectHeight":500,"airRouteSegmentSeq":4}],"flightLineName":"起降场yfk起降场1-离场点-航路G00101-G00102-G00103-G00104-起降场算法测试-起降场1-进场点","departureAirportId":"40307655171948544","departureAirportName":"yfk起降场1","departurePointLon":120.703171,"departurePointLat":31.333761,"departurePointHeight":"","takeoffPointLon":120.717384,"takeoffPointLat":31.338784,"takeoffPointHeight":"","arrivalAirportId":"23557376825163776","arrivalAirportName":"算法测试-起降场1","arrivalPointLon":120.70778,"arrivalPointLat":31.338022,"arrivalPointHeight":"","landPointLon":120.711524,"landPointLat":31.338268,"landPointHeight":""}],"airspaceType":"NON_SEGREGATED","isDraft":false