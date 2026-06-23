


# 登录鉴权：
 获取认证信息 请求方式：POST  url: http://[IP]:8801/iomp/api/v2/token  
    请求参数：accesskey
    返回报文体：
        jwtToken	string	一串base64字符串（默认有效期 30 min）
        refreshToken	string	字符串, 用于刷新 token 令牌的授权码, 在下次刷新或登录前有效
刷新认证信息  请求方式：POST url: http://[IP]:8801/iomp/api/v2/token/refresh  #描述： 通过 refreshToken 生成新的 jwtToken 令牌
    请求参数：refreshToken
    返回报文体：
        jwtToken	string	新的 jwtToken
        efreshToken	string	新的 refreshToken
访问续期 请求方式：GET  url: http://[IP]:8801/iomp/api/v2/token/access
获取当前登录人username 请求方式：GET  url: http://[IP]:8801/iomp/api/v2/token/user
    请求头（headers）：Authorization  string	{jwtToken}
    返回body中json：username字段 
# 集群信息
查询集群资源信息 请求方式：GET  url: http://[IP]:8801/iomp/api/v2/cluster/{clusterName}
    clusterName	string	是	集群名称，后续可以作为集群唯一标志，字母+数字
    返回值：
        code	int	状态码
        status	int	状态值
        timestamp	long	时间戳
        result	Object	集群对象
        result对象：
            id	string	集群id
            k8sName	string	集群名称
            k8sSign	string	集群标识
            createTime	long	集群创建时间/接入时间
            description	string	集群描述
            dnsIp	string	集群dns地址，多个以逗号隔开
            ntpServer	string	集群ntp服务器地址
            osArch	string	集群架构,linux/amd64、linux/arm64
            timezone	string	集群时区，比方Asia/Shanghai
            workMode	string	集群访问模式，bgp、ipip
查询指定空间资源信息      请求方式：GET          url: http://[IP]:8801/iomp/api/v2/cluster/{clusterName}/{namespace} 
    clusterName	string	是	集群名称，后续可以作为集群唯一标志，字母+数字
    namespace	string	是	部署到的空间
    返回值：
        code	int	状态码
        status	int	状态值
        timestamp	long	时间戳
        result	Object	空间对象
        result对象：
            clusterId	string	集群id
            name	string	空间标识
            showName	string	空间名称
            createTime	long	空间创建时间
            description	string	空间描述
            level	string	空间等级
            publice	int	空间属性，0: 私有 ；1:公有
            regionNames	string	空间绑定的域名称
            regionSigns	string	空间绑定的域标识
            timezone	string	空间时区，比方Asia/Shanghai
查询指定服务部署的相关信息 请求方式：GET url: http://[IP]:8801/iomp/api/v2/cluster/{clusterName}/{namespace}/{kind}/{name}
    clusterName	string	是	集群名称，后续可以作为集群唯一标志，字母+数字
    namespace	string	是	部署到的空间
    kind	string	是	资源类型
    name	string	是	k8s服务资源名称
    kind 的定义， 如下每一项，（pod控制器）
        Deployment  string	否	部署无状态应用
        StatefulSet  string	否	部署有状态应用
        DaemonSet  string	否	在每一个Node上运行的Pod
        Pod  string	否	k8s服务资源名称
        Service  string	否	是一种可以访问 Pod逻辑分组的策略，能够提供负载均衡的能力
        Ingress  string	否	网关规则
        ConfigMap  string	否	配置文件，包含 kubert、 服务、策略等
        Secret  string	否	秘钥证书资源
        Job  string	否	Job分为普通任务（Job）和定时任务（CronJob），指一次性执行。应用场景：离线数据处理，视频解码等业务
        CronJob  string	否	周期性任务，像Linux的Crontab一样。应用场景：通知，备份
        PVC  string	否	存储声明
        PV  string	否	集群级别资源，存储对象
获取项目的配置（统一配置）  请求方式：GET   http://[IP]:8801/iomp/api/v2/cluster/cloudtest3/dp/ConfigMap/project-clog          
    说明： 请求接口的  {name} 路径  ，在获取对应的服务配置 ，对应value：   project-XXX （XXX标识服务名称）；cloudtest3集群，dp空间 ，clog 的配置信息
    返回值：
        code	int	状态码
        status	int	状态值
        timestamp	long	时间戳
        result	Object	配置对象
获取主机当前时间 请求方式：GET  url: http://[IP]:8801/iomp/api/v2/node/current-time 
    请求参数 hostIp	string	是	主机IP地址
    返回值：
        code	int	状态码
        status	int	状态值
        timestamp	long	时间戳
        result	string	主机当前时间时间戳
# 服务管理
1 查询服务–通过标签查询pods
请求方式：POST
url: http://[IP]:8801/iomp/api/v2/service/{clusterName}/{namespace}/{kind}
参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    kind	string	是	资源类型
body参数（如果参数中某个属性为存在 all 属性，则删除服务上所有对应参数内容）：
    labels	Map<String, String>	是	标签
返回分页结果：见下边 2 返回结构

2 查询服务
请求方式：GET
url: http://[IP]:8801/iomp/api/v2/service/{clusterName}/{namespace}/{kind}/{deployName}
参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    kind	string	是	资源类型
    deployName	string	是	服务名
body参数（如果参数中某个属性为存在 all 属性，则删除服务上所有对应参数内容）：
    labels	Map<String, String>	否	标签
kind 的属性， 如下每一项，（pod控制器）：
    All	string	否	如果kind填写此属性则查询服务资源属性 deployment/statefulset/daemonset 上查询，一般业务默认写这个就可以
返回分页结果：
    creationTimestamp	string	创建时间，对应k8s上服务信息，LastTransitionTime 字段——用于记录上一次事务运行时间
    name	string	服务名
    namespace	string	命名空间
    kind	string	Deployment/StatusfulSet/DaemonSet
    readyReplicas	integer	ready 状态的副本数
    replicas	integer	期望的副本数
    pods	List<Object>	pod 对象数组；1、labels没有匹配上，则返回到对应服务(deployName)的pod;，labels匹配上，会返回所以对应labels的pod以及服务(deployName)pod;
    返回的是原生的Pod对象，字段可以参考 Pod对象的Yaml的数据结构来获取

3 删除服务
请求方式：DELETE
url: http://[IP]:8801/iomp/api/v2/service/{clusterName}/{namespace}/{deployName}
url参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    deployName	string	是	服务名
删除服务相关资源服务 
body参数（如果参数中某个属性为存在 all 属性，则删除服务上所有对应参数内容）：
    configmaps	string[]	否	配置文件	
    ingresses	string[]	否	路由	
    secrets	string[]	否	秘钥	
    pvcs	string[]	否	pvc存储声明	
参数也可以通过url的方式调用， 下边为使用url的方式定义; 两种方式选择一种就可以； 
url（如果参数中某个属性为存在 all 属性，则删除服务上所有对应参数内容）：
    configmaps	string	否	配置文件，多个名称用逗号隔开	http://xxx ? configmaps=project-clog, project-test&ingresses=a, b
    ingresses	string	否	路由，多个名称用逗号隔开	http://xxx ? configmaps=all&ingresses=all
    secrets	string	否	秘钥，多个名称用逗号隔开	
    pvcs	string	否	pvc存储声明，多个名称用逗号隔开	
返回报文体: 
    result	string	success

4  一键删除服务
请求方式：DELETE
url: http://[IP]:8801/iomp/api/v1/service/{clusterName}/{namespace}/{deployName}/all
url参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    deployName	string	是	服务名
    ignore	Boolean	否	以Body的方式传参（目前只支持忽略pvc共享删除的问题）
    true： 忽略校验提示
    默认不传则是 false；
我们删除一个服务的时候， 如果服务使用的pvc被其他服务也使用了； 那么会提示"无法删除， pvc已经被占用"
这里如果传输true， 那么就不会做这个提示；按规范进行删除
返回报文体: 
    result	string	success

5 一键删除服务(支持Job作为服务的一键删除方式)
请求方式：DELETE
url: http://[IP]:8801/iomp/api/v2/service/{clusterName}/{namespace}/{deployName}/all
url参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    deployName	string	是	服务名
    ignore	Boolean	否	以Body的方式传参（目前只支持忽略pvc共享删除的问题）
    true： 忽略
返回: 
    result	string	success

6 重启服务接口
请求方式：DELETE
url: http://[IP]:8801/iomp/api/v2/service/reboot/{clusterName}/{namespace}/{deployName}
url参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    deployName	string	是	服务名
返回: 
    result	string	success

7 修改服务属性
请求方式：PATCH
url: http://[IP]:8801/iomp/api/v2/service/{clusterName}/{namespace}/{deployName}
url参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    deployName	string	是	服务名
body参数；要修改的服务参数：
    replicas	number	否	服务实例数， 参考页面的scale方法	
    2.6.3.4+
    2.5.9.2+
返回: 
    result	string	success

8 获取服务相关资源
请求方式：GET
url: http://[IP]:8801/iomp/api/v2/service/relate/{clusterName}/{namespace}/{deployName}
url参数说明：
    clusterName	string	是	集群名称
    namespace	string	是	命名空间
    deployName	string	是	服务名
返回结果：
    result	Object	返回的是服务的相关资源
result返回值：
    configmaps	数组	["clog-clog", "clog-sdk-clog", "command-clog", "project-clog"]
    ingresses	数组	["clog-2322-awfbo"]
    jobs	数组	[]
    pvcs	数组	[]
    secrets	数组	[]
    services	数组	[]