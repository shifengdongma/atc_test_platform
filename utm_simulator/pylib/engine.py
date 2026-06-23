"""
pylib/engine.py
封装底层 C++ 接口为 Pythonic 的类方法。
负责加载 DLL 并配置函数签名。
"""
import ctypes
import os
from typing import List, Optional
from .structs import *

class UTMEngine:
    def __init__(self, lib_path: str = None):
        """ 初始化引擎，加载动态库 """
        if lib_path is None:
            # 默认查找 ../build/utm_core.dll 或 .so
            base_dir = os.path.dirname(os.path.abspath(__file__))
            lib_path = os.path.join(base_dir, "..", "build", "libutm_core.so")
            if not os.path.exists(lib_path):
                lib_path = lib_path.replace(".so", ".dll") # Try Windows

        if not os.path.exists(lib_path):
            raise FileNotFoundError(f"UTM Core Library not found at: {lib_path}")

        self.lib = ctypes.CDLL(lib_path)
        self._init_signatures()

    def _init_signatures(self):
        """ 绑定 C 函数签名 (argtypes/restype) """
        
        # 1. PredictTrajectory
        self.lib.PredictTrajectory.argtypes = [
            ctypes.POINTER(AircraftStateInput), # 变更
            ctypes.POINTER(FlightPlan), 
            ctypes.c_double, ctypes.c_double, 
            ctypes.POINTER(TrajectoryPoint), ctypes.c_int
        ]
        self.lib.PredictTrajectory.restype = ctypes.c_int

        # 2. DetectTacticalConflict
        self.lib.DetectTacticalConflict.argtypes = [
        ctypes.POINTER(AircraftStateInput), ctypes.c_int, # 变更
        ctypes.POINTER(ctypes.POINTER(FlightPlan)), ctypes.c_int,
        ctypes.c_double,
        ctypes.POINTER(DynamicNoFlyZone), ctypes.c_int,   # 变更
        ctypes.POINTER(ConflictInfo), ctypes.c_int
    ]
        # 3. CheckDeviation
        self.lib.CheckDeviation.argtypes = [ctypes.POINTER(TelemetryData), ctypes.POINTER(FlightPlan)]
        self.lib.CheckDeviation.restype = DeviationInfo

        # 4. DetectStrategicConflict
        self.lib.DetectStrategicConflict.argtypes = [
            ctypes.POINTER(FlightPlan),
            ctypes.POINTER(ctypes.POINTER(FlightPlan)), ctypes.c_int,
            ctypes.POINTER(DynamicNoFlyZone), ctypes.c_int, # [新增参数]
            ctypes.POINTER(ConflictInfo), ctypes.c_int
        ]

        self.lib.ComputeVelocityVector.argtypes = [ctypes.POINTER(TelemetryData)]
        self.lib.ComputeVelocityVector.restype = None

        # void InitDefaultSystemConfig()
        self.lib.InitDefaultSystemConfig.argtypes = []
        self.lib.InitDefaultSystemConfig.restype = None

        # void UpdateSystemConfig(const SystemConfig* config)
        self.lib.UpdateSystemConfig.argtypes = [ctypes.POINTER(SystemConfig)]
        self.lib.UpdateSystemConfig.restype = None

        # 5. CalculatePairwiseMinDistance
        self.lib.CalculatePairwiseMinDistance.argtypes = [
            ctypes.POINTER(AircraftStateInput), ctypes.POINTER(FlightPlan),
            ctypes.POINTER(AircraftStateInput), ctypes.POINTER(FlightPlan),
            ctypes.c_double, ctypes.c_double
        ]
        self.lib.CalculatePairwiseMinDistance.restype = PairwiseDistResult

        # 6. DetectPreFlightConflict
        self.lib.DetectPreFlightConflict.argtypes = [
            ctypes.POINTER(FlightPlan),             # subject_plan
            ctypes.POINTER(AircraftStateInput),     # others
            ctypes.c_int,                           # other_count
            ctypes.POINTER(ctypes.POINTER(FlightPlan)), # other_plans (double pointer)
            ctypes.c_int,                           # other_plan_count
            ctypes.POINTER(DynamicNoFlyZone),       # nfzs
            ctypes.c_int,                           # nfz_count
            ctypes.c_double,                        # lookahead_time
            ctypes.POINTER(ConflictInfo),           # output
            ctypes.c_int                            # max_out
        ]
        self.lib.DetectPreFlightConflict.restype = ctypes.c_int

    # --- 高级封装接口 ---

    def compute_vector(self, telemetry_obj: TelemetryData):
        """
        调用 C++ 计算速度向量并回填到 telemetry_obj.velocity 中
        """
        # 使用 ctypes.byref 传递引用（指针）
        self.lib.ComputeVelocityVector(ctypes.byref(telemetry_obj))


    def predict_trajectory(self, 
                           telemetry: dict, # [修改] 传入包含 current/history 的字典
                           plan: Optional[FlightPlan], 
                           horizon=60.0, step=1.0) -> List[TrajectoryPoint]:
        try:
            max_pts = int(horizon / step) + 5
            out_buf = (TrajectoryPoint * max_pts)()
            plan_ptr = ctypes.pointer(plan) if plan else None
            
            tel = TelemetryData()
            tel.uid = telemetry['uid'].encode('utf-8')
            tel.location = GeoPoint(**telemetry['current']['location'])
            tel.velocity = Vec3(**telemetry['current']['velocity'])
            tel.classification = telemetry['current']['classification']
            tel.speed = telemetry['current']['speed']
            tel.heading = telemetry['current']['heading']
            tel.verticalSpeed = telemetry['current']['verticalSpeed']
            tel.longitudinal_threshold = telemetry['current']['longitudinal_threshold']
            tel.lateral_threshold = telemetry['current']['lateral_threshold']
            tel.v_threshold = telemetry['current']['v_threshold']
            tel.timestamp = telemetry['current']['timestamp']
            tel.operatingStatus = telemetry["current"]['operatingStatus']
            tel.relativeAltitude = telemetry["current"]['relativeAltitude']
            tel.ressureAltitude = telemetry["current"]['ressureAltitude']
            tel.coordinateSystemType = telemetry["current"]['coordinateSystemType']
            tel.verticalAccuracy = telemetry["current"]['verticalAccuracy']
            tel.horizontalAccuracy = telemetry["current"]['horizontalAccuracy']
            tel.speedAccuracy = telemetry["current"]['speedAccuracy']
            tel.timestampAccuracy = telemetry["current"]['timestampAccuracy']
            # 构造 AircraftStateInput
            input_struct = AircraftStateInput()
            input_struct.uid = bytes(telemetry['uid'], encoding='utf-8')
            input_struct.current = tel
            
            hist_list = telemetry.get('history', [])
            count = len(hist_list)
            input_struct.history_count = count
            
            # 必须保持引用
            self._pred_keep_alive = [] 
            
            if count > 0:
                SnapshotArray = TelemetrySnapshot * count
                hist_arr = SnapshotArray()
                for i, d in enumerate(hist_list):
                    hist_arr[i].timestamp = d['timestamp']
                    hist_arr[i].location  = GeoPoint(**d['location'])
                    hist_arr[i].h_accuracy = d['h_accuracy']
                    hist_arr[i].v_accuracy = d['v_accuracy']
                    hist_arr[i].speed_accuracy = d['speed_accuracy']
                    hist_arr[i].speed = d['speed']
                    hist_arr[i].heading = d['heading']
                    hist_arr[i].verticalSpeed = d['verticalSpeed']
                self._pred_keep_alive.append(hist_arr)
                input_struct.history = hist_arr
            else:
                input_struct.history = None
            
            # 调用 C++
            # print(f'PredictTrajectory begin')
            count = self.lib.PredictTrajectory(
                ctypes.byref(input_struct), 
                plan_ptr, 
                horizon, step, 
                out_buf, max_pts
            )
            # print(f'PredictTrajectory end')
            return [out_buf[i] for i in range(count)]
        except Exception as e:
            print(f'predict_trajectory error:{e}')


    def detect_tactical_conflicts(self, 
                                  telemetries: List[dict], # 格式需调整，包含 history
                                  active_plans: List[FlightPlan], 
                                  nfz_list: List[DynamicNoFlyZone], 
                                  lookahead=120.0) -> List[ConflictInfo]:
        try:
            n_input = len(telemetries)
            if n_input == 0: return []

            # 构造 AircraftStateInput 数组
            input_arr = (AircraftStateInput * n_input)()
            
            # 必须保持引用防止 GC
            self._history_keep_alive = []

            for i, item in enumerate(telemetries):
                # 1. 填充 current
                input_arr[i].uid = item['current'].uid
                input_arr[i].current = item['current']
                
                # 2. 填充 history
                hist_list = item.get('history', [])
                count = len(hist_list)
                input_arr[i].history_count = count
                
                if count > 0:
                    hist_arr = (TelemetrySnapshot * count)(*hist_list)
                    self._history_keep_alive.append(hist_arr) # 关键！
                    input_arr[i].history = hist_arr
                else:
                    input_arr[i].history = None

            # 构造 Plan 指针数组
            plan_ptrs_arr = (ctypes.POINTER(FlightPlan) * len(active_plans))()
            for i, p in enumerate(active_plans):
                plan_ptrs_arr[i] = ctypes.pointer(p)
                
            nfz_arr = (DynamicNoFlyZone * len(nfz_list))(*nfz_list)
            
            max_res = 50000
            res_arr = (ConflictInfo * max_res)()
            
            count = self.lib.DetectTacticalConflict(
                input_arr, n_input,
                plan_ptrs_arr, len(active_plans),
                lookahead,
                nfz_arr, len(nfz_list),
                res_arr, max_res
            )
            # 解析结果

            return [res_arr[i] for i in range(count)]
        except Exception as e:
            print(f'detect_tactical_conflicts error:{e}')



    def check_deviation(self, tel: TelemetryData, plan: FlightPlan) -> DeviationInfo:
        return self.lib.CheckDeviation(ctypes.byref(tel), ctypes.byref(plan))

    def detect_strategic(self, new_plan: FlightPlan, active_plans: List[FlightPlan], nfz_list: List[DynamicNoFlyZone]) -> List[ConflictInfo]:
        try:
            # 处理 Existing Plans 指针数组
            ptrs = (ctypes.POINTER(FlightPlan) * len(active_plans))()
            for i, p in enumerate(active_plans):
                ptrs[i] = ctypes.pointer(p)
                
            # 处理 NFZ 数组 (这是一个结构体数组，不是指针数组)
            if nfz_list:
                nfz_arr = (DynamicNoFlyZone * len(nfz_list))(*nfz_list)
                nfz_count = len(nfz_list)
            else:
                nfz_arr = None
                nfz_count = 0
                
            max_res = 50
            res_arr = (ConflictInfo * max_res)()
            
            count = self.lib.DetectStrategicConflict(
                ctypes.byref(new_plan), 
                ptrs, len(active_plans),
                nfz_arr, nfz_count, # [新增传入]
                res_arr, max_res
            )
            
            return [res_arr[i] for i in range(count)]
        except Exception as e:
            print(f'detect_strategic error:{e}')

    def init_default_config(self):
        """ 初始化 C++ 内部的默认安全规则 """
        if hasattr(self.lib, 'InitDefaultSystemConfig'):
            self.lib.InitDefaultSystemConfig()

    def update_config(self, config_obj: SystemConfig):
        """ 
        热更新系统规则配置 
        :param config_obj: 已填充数据的 SystemConfig 结构体实例
        """
        if hasattr(self.lib, 'UpdateSystemConfig'):
            self.lib.UpdateSystemConfig(ctypes.byref(config_obj))

    def apply_business_rules(self,json_data):
        """
        解析业务 JSON 配置并热更新到底层 C++ 引擎
        """
        print("[Config] Applying business rules...")
        cfg = SystemConfig()
        
        # -------------------------------------------------
        # 1. 填充机间碰撞规则 (Collision Rules)
        # -------------------------------------------------
        # 处理 collisionShortAlertProperties
        alert_props = json_data.get("collisionShortAlertProperties", {})

        dists = alert_props.get("distances", {})
        for size_key, params in dists.items():
            idx = SIZE_MAP.get(size_key, 2) # 默认 SMALL
            rule = cfg.collision_alert[idx] # 获取数组中的引用
            
            rule.rule_id = params.get("violateRuleId", f"DEF_AL_{size_key}").encode('utf-8')
            rule.longitudinal = float(params.get("longitudinal", 0))
            rule.transverse = float(params.get("transverse", 0))
            rule.vertical = float(params.get("vertical", 0))
            rule.duration = 0.0 # Alert 通常基于瞬时距离
            rule.enabled = alert_props.get("enabled", True)

        # 处理 collisionShortWarnProperties
        warn_props = json_data.get("collisionShortWarnProperties", {})

        dists = warn_props.get("distances", {})
        common_dur = float(warn_props.get("duration", 60))
        for size_key, params in dists.items():
            idx = SIZE_MAP.get(size_key, 2)
            rule = cfg.collision_warn[idx]
            
            rule.rule_id = params.get("violateRuleId", f"DEF_WN_{size_key}").encode('utf-8')
            rule.longitudinal = float(params.get("longitudinal", 0))
            rule.transverse = float(params.get("transverse", 0))
            rule.vertical = float(params.get("vertical", 0))
            rule.duration = common_dur
            rule.enabled = warn_props.get("enabled", True)

        # -------------------------------------------------
        # 2. 填充空域入侵规则 (Airspace Rules)
        # -------------------------------------------------
        # JSON 结构: airspaceEnterAlertProperties -> { "danger": { "LARGE": {...} }, "noDrone": ... }
        # C++ 结构: airspace_alert[NFZ_TYPE][UAV_SIZE]
        
        as_alert = json_data.get("airspaceEnterAlertProperties", {})
        for type_key, size_dict in as_alert.items():
            type_idx = NFZ_TYPE_MAP.get(type_key)
            if type_idx is None: continue
            
            for size_key, params in size_dict.items():
                if size_key == "enabled": continue # 跳过 enabled 字段
                
                size_idx = SIZE_MAP.get(size_key, 2)
                rule = cfg.airspace_alert[type_idx][size_idx]
                
                rule.rule_id = params.get("violateRuleId", "").encode('utf-8')
                rule.longitudinal = float(params.get("longitudinal", 0))
                rule.transverse = float(params.get("transverse", 0))
                rule.vertical = 0.0 # 空域通常看水平和高度层，这里简化处理
                rule.enabled =size_dict.get("enabled", True)



        # -------------------------------------------------
        # 2.2 填充空域入侵警告规则 (Airspace Warn Rules)
        # -------------------------------------------------
        # JSON 结构: airspaceEnterWarnProperties -> { "danger": { "enabled": true, "LARGE": {...} }, ... }
        # C++ 结构: airspace_warn[NFZ_TYPE][UAV_SIZE]
        
        as_warn = json_data.get("airspaceEnterWarnProperties", {})
        
        for type_key, size_dict in as_warn.items():
            # 1. 获取空域类型索引 (如 danger -> 5)
            type_idx = NFZ_TYPE_MAP.get(type_key,None)
            if type_idx is None:
                continue # 跳过未知的空域类型
            

            # 3. 遍历不同机型 (LARGE, MEDIUM, SMALL...)
            for size_key, params in size_dict.items():
                # 跳过非机型字段 (如 "enabled")
                if size_key == "enabled":
                    continue
                
                # 获取机型索引 (默认 SMALL)
                size_idx = SIZE_MAP.get(size_key, 2)
                
                # 获取 C++ 结构体数组中的引用
                rule = cfg.airspace_warn[type_idx][size_idx]
                
                # 4. 填充具体参数
                # 注意: encode('utf-8') 用于将 Python 字符串转为 C char[]
                rule.rule_id = params.get("violateRuleId", f"DEF_AS_WN_{type_key}_{size_key}").encode('utf-8')
                
                # 距离阈值
                rule.longitudinal = float(params.get("longitudinal", 0))
                rule.transverse = float(params.get("transverse", 0))
                
                # 垂直阈值 (JSON 中未提供垂直字段，暂时设为0或与横向相同，视业务需求定)
                # 如果业务后续增加了 vertical 字段，这里改为 params.get("vertical", 0)
                rule.vertical = float(params.get("vertical", 0))
                
                # 预测时间 (Duration) - 警告规则通常包含时间预测 (如 30s)
                rule.duration = float(params.get("duration", 0))
                
                # 标记为启用
                rule.enabled = size_dict.get("enabled", True)

        # -------------------------------------------------
        # 3. 填充偏航规则 (Deviation)
        # -------------------------------------------------
        dev_alert = json_data.get("deviationAlertProperties", {})

        cfg.deviation_alert.rule_id = dev_alert.get("violateRuleId", "DEV_AL").encode('utf-8')
        # 假设偏航固定阈值，或者从 JSON 读取数值
        cfg.deviation_alert.transverse = 50.0 
        cfg.deviation_alert.enabled =dev_alert.get("enabled")

        dev_warn = json_data.get("deviationWarnProperties", {})

        cfg.deviation_warn.rule_id = dev_warn.get("violateRuleId", "DEV_AL").encode('utf-8')
        # 假设偏航固定阈值，或者从 JSON 读取数值
        cfg.deviation_warn.transverse = 50.0 
        cfg.deviation_warn.enabled =dev_warn.get("enabled")
        rule.duration = float(params.get("duration", 0))



        # -------------------------------------------------
        # 4. 调用引擎接口注入
        # -------------------------------------------------
        try:
            # 假设 sim_manager 是全局单例
            self.update_config(cfg)
            print("[Config] Successfully updated C++ engine configuration.")
        except Exception as e:
            print(f"[Config] Error updating engine: {e}")

    def calculate_pairwise_distance(self, 
                                    tel1: dict, plan1: Optional[FlightPlan],
                                    tel2: dict, plan2: Optional[FlightPlan],
                                    lookahead=60.0, step=1.0) -> dict:
        """
        计算两机未来一段时间内的精确最小距离
        """
        # 1. 构造 AircraftStateInput 1
        input1 = AircraftStateInput()
        input1.uid = tel1['current'].uid
        input1.current = tel1['current']
        input1.history_count = len(tel1.get('history', []))
        if input1.history_count > 0:
            input1.history = (TelemetrySnapshot * input1.history_count)(*tel1['history'])
        
        # 2. 构造 AircraftStateInput 2
        input2 = AircraftStateInput()
        input2.uid = tel2['current'].uid
        input2.current = tel2['current']
        input2.history_count = len(tel2.get('history', []))
        if input2.history_count > 0:
            input2.history = (TelemetrySnapshot * input2.history_count)(*tel2['history'])

        # 3. 处理 FlightPlan 指针
        p1_ptr = ctypes.pointer(plan1) if plan1 else None
        p2_ptr = ctypes.pointer(plan2) if plan2 else None

        # 4. 调用 C++
        res = self.lib.CalculatePairwiseMinDistance(
            ctypes.byref(input1), p1_ptr,
            ctypes.byref(input2), p2_ptr,
            lookahead, step
        )

        # 5. 转换为 Python 字典返回
        if not res.success:
            return None
            
        return {
            "min_distance": res.min_distance,
            "time_stamp": res.time_stamp,
            "subject": {
                "lat": res.pos_subject.lat, 
                "lon": res.pos_subject.lon, 
                "alt": res.pos_subject.alt,
                "vx": res.vel_subject.x,
                "vy": res.vel_subject.y,
                "vz": res.vel_subject.z
            },
            "object": {
                "lat": res.pos_object.lat, 
                "lon": res.pos_object.lon, 
                "alt": res.pos_object.alt,
                "vx": res.vel_object.x,
                "vy": res.vel_object.y,
                "vz": res.vel_object.z
            }
        }
    



    # 在 UTMEngine 类中添加高层方法:
    def detect_pre_flight_conflicts(self, 
                                    subject_plan: FlightPlan, 
                                    telemetries: List[dict], 
                                    active_plans: List[FlightPlan], # 其他人的计划
                                    nfz_list: List[DynamicNoFlyZone], 
                                    lookahead=1200.0) -> List[ConflictInfo]:
        
        # 1. 准备 Others State Input
        n_input = len(telemetries)
        input_arr = (AircraftStateInput * n_input)()
        self._pf_keep_alive = [] # 防止 GC

        for i, item in enumerate(telemetries):
            input_arr[i].uid = item['current'].uid
            input_arr[i].current = item['current']
            hist = item.get('history', [])
            count = len(hist)
            input_arr[i].history_count = count
            if count > 0:
                h_arr = (TelemetrySnapshot * count)(*hist)
                self._pf_keep_alive.append(h_arr)
                input_arr[i].history = h_arr
            else:
                input_arr[i].history = None

        # 2. 准备 Others Plans
        # 构建 map 以便快速查找，这里其实只需要传数组，C++会自己匹配UID
        # 注意：active_plans 可能包含 subject_plan 自身吗？业务层应排除
        plan_ptrs = (ctypes.POINTER(FlightPlan) * len(active_plans))()
        for i, p in enumerate(active_plans):
            plan_ptrs[i] = ctypes.pointer(p)

        # 3. 准备 NFZ
        nfz_arr = (DynamicNoFlyZone * len(nfz_list))(*nfz_list) if nfz_list else None
        nfz_count = len(nfz_list) if nfz_list else 0

        # 4. 准备输出
        max_res = 1000 # 预飞检测不需要返回太多，只要有阻挡即可
        res_arr = (ConflictInfo * max_res)()

        # 5. 调用
        count = self.lib.DetectPreFlightConflict(
            ctypes.byref(subject_plan),
            input_arr, n_input,
            plan_ptrs, len(active_plans),
            nfz_arr, nfz_count,
            lookahead,
            res_arr, max_res
        )

        return [res_arr[i] for i in range(count)]

