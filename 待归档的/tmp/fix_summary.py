import sys

path = r"c:\Users\wdjlw\iCloudDrive\Atc_Test2026\utm_moc52_develop\utm_test_cases\高可用测试\高可用集群切换测试.py"

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''        def _fmt_cost(r):
            if r.get("all_costs_str"):
                old_m = r.get("failover_old_master", "")
                new_m = r.get("failover_new_master", "")
                direction =


def main():
    """主函数"""
    tester = HighAvailabilityClusterTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()'''

new_code = '''        def _fmt_cost(r):
            if r.get("all_costs_str"):
                d = f"({r.get('failover_old_master','')}→{r.get('failover_new_master','')})" if r.get('failover_old_master') and r.get('failover_new_master') else ""
                return f"{r['all_costs_str']}ms{d}"
            elif r.get("failover_cost_ms"):
                d = f"({r.get('failover_old_master','')}→{r.get('failover_new_master','')})" if r.get('failover_old_master') and r.get('failover_new_master') else ""
                return f"{r['failover_cost_ms']}ms{d}"
            return f"注入故障{r.get('master_node','未知')} daemon日志未检索到"

        def _fmt_duration(r):
            s, e = r.get("start_time",""), r.get("end_time","")
            if s and e:
                try:
                    from datetime import datetime
                    ds = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
                    de = datetime.strptime(e, "%Y-%m-%d %H:%M:%S.%f")
                    return f"{(de-ds).total_seconds():.1f}s"
                except Exception:
                    pass
            return "-"

        def _fmt_es(r):
            es = r.get("es_status", "未检查")
            return "一致" if "一致" in es else "不一致" if "不一致" in es else "未检查"

        def _fmt_svc(r):
            svc = r.get("services_status", "未检查")
            return "正常" if "正常" in svc else "异常" if "异常" in svc or "失败" in svc else "未检查"

        def _fmt_alert(r):
            return r.get("master_alert_status", "未检查")

        def _fmt_status(r):
            return "场景测试结果 不通过" if r.get("error") else "场景测试结果 通过"

        self.logger.section("测试汇总报告")
        self.logger.success("测试完成！")

        # 整合表格
        print(f"\\n{'='*160}")
        print("服务名                     轮次 主集群          切换时间   副本 缩容 切换耗时                            耗时     ES   服务 存储告警 结果")
        print(f"{'-'*160}")

        for result in self.results:
            service_name = result["service_name"]
            round_results = result.get("round_results", [])

            if not round_results:
                status_label = "场景测试结果 不通过" if result.get("error") else "场景测试结果 通过"
                print(f"{service_name:<24} {'-':<4} {'-':<16} {'-':<10} {'-':<4} {'-':<4} {'-':<36} {'-':<8} {'-':<6} {'-':<6} {'-':<10} {status_label}")
                if result.get("error"):
                    print(f"  异常信息: {result['error']}")
                continue

            svc_pass = 0
            svc_fail = 0
            for r in round_results:
                status_label = _fmt_status(r)
                if r.get("error"):
                    svc_fail += 1
                else:
                    svc_pass += 1

                print(
                    f"{service_name:<24} "
                    f"{r['round']:<4} "
                    f"{_fmt_master(r):<16} "
                    f"{_fmt_switch_time(r):<10} "
                    f"{r.get('original_replicas') or '-':<4} "
                    f"{'是' if r.get('scale_down_ok') else '否':<4} "
                    f"{_fmt_cost(r):<36} "
                    f"{_fmt_duration(r):<8} "
                    f"{_fmt_es(r):<6} "
                    f"{_fmt_svc(r):<6} "
                    f"{_fmt_alert(r):<10} "
                    f"{status_label}"
                )
                if r.get("error"):
                    print(f"  异常信息: {r['error']}")

            print(f"{'-'*160}")
            print(f"测试 {service_name} | 通过：{svc_pass} | 失败：{svc_fail}")

        print(f"{'='*160}")

        # 全量统计
        self.logger.info(f"总服务数: {total_count}")
        self.logger.info(f"成功服务数: {success_count}")
        self.logger.info(f"失败服务数: {failed_count}")
        self.logger.info(f"跳过服务数: {skipped_count}")
        self.logger.info(f"成功率: {success_count/total_count*100:.1f}%")

        # 切换性能统计
        all_costs = []
        all_switch_events = []
        for result in self.results:
            if result["status"] == "completed":
                if result["failover_cost_ms"]:
                    all_costs.append(result["failover_cost_ms"])
                all_switch_events.extend(result["switch_events"])

        if all_costs:
            avg_cost = sum(all_costs) / len(all_costs)
            self.logger.info(f"总切换次数: {len(all_switch_events)}")
            self.logger.info(f"平均切换耗时: {avg_cost:.0f}ms")
            fast_switches = [c for c in all_costs if c < 5000]
            slow_switches = [c for c in all_costs if c >= 5000]
            self.logger.info(f"快速切换(<5s): {len(fast_switches)} 次")
            self.logger.info(f"慢速切换(>=5s): {len(slow_switches)} 次")

        # 存储一致性统计
        redis_stats = {"正常": 0, "异常": 0, "检查失败": 0}
        es_stats = {"正常": 0, "异常": 0, "检查失败": 0}
        dm_stats = {"正常": 0, "异常": 0, "检查失败": 0}
        for result in self.results:
            if result["status"] == "completed":
                redis_status = result["storage_results"]["redis"]
                es_status = result["storage_results"]["es"]
                dm_status = result["storage_results"]["dm"]
                if redis_status == "一致":
                    redis_stats["正常"] += 1
                elif redis_status == "不一致":
                    redis_stats["异常"] += 1
                else:
                    redis_stats["检查失败"] += 1
                if es_status == "一致":
                    es_stats["正常"] += 1
                elif es_status == "不一致":
                    es_stats["异常"] += 1
                else:
                    es_stats["检查失败"] += 1
                if dm_status == "一致":
                    dm_stats["正常"] += 1
                elif dm_status == "不一致":
                    dm_stats["异常"] += 1
                else:
                    dm_stats["检查失败"] += 1

        self.logger.info(f"Redis 一致性: {redis_stats['正常']}/{success_count} 正常, {redis_stats['异常']} 异常, {redis_stats['检查失败']} 检查失败")
        self.logger.info(f"ES 一致性: {es_stats['正常']}/{success_count} 正常, {es_stats['异常']} 异常, {es_stats['检查失败']} 检查失败")
        self.logger.info(f"DM 一致性: {dm_stats['正常']}/{success_count} 正常, {dm_stats['异常']} 异常, {dm_stats['检查失败']} 检查失败")

        # 写入详细报告文件
        report_file = os.path.join(self.output_dir, f"ha_cluster_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"高可用集群切换测试报告 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
            f.write("=" * 100 + "\\n\\n")
            f.write("1. 测试统计\\n")
            f.write("-" * 50 + "\\n")
            f.write(f"总服务数: {total_count}\\n")
            f.write(f"成功服务数: {success_count}\\n")
            f.write(f"失败服务数: {failed_count}\\n")
            f.write(f"跳过服务数: {skipped_count}\\n")
            f.write(f"成功率: {success_count/total_count*100:.1f}%\\n\\n")

            f.write("2. 各服务详细结果\\n")
            f.write("-" * 50 + "\\n")
            for result in self.results:
                service_name = result["service_name"]
                f.write(f"\\n服务: {service_name}\\n")
                round_results = result.get("round_results", [])
                if round_results:
                    svc_pass = sum(1 for r in round_results if not r.get("error"))
                    svc_fail = sum(1 for r in round_results if r.get("error"))
                    f.write(f"通过: {svc_pass} | 失败: {svc_fail}\\n")
                    for r in round_results:
                        status = "通过" if not r.get("error") else "不通过"
                        cost = r.get("all_costs_str") or r.get("failover_cost_ms") or "-"
                        f.write(f"  轮次{r['round']}: {status}, 切换耗时: {cost}ms\\n")
                        if r.get("error"):
                            f.write(f"    异常: {r['error']}\\n")
                else:
                    f.write(f"状态: {result['status']}\\n")
                    if result.get("error"):
                        f.write(f"错误: {result['error']}\\n")
                f.write("\\n")

            if all_costs:
                f.write("3. 切换性能\\n")
                f.write("-" * 50 + "\\n")
                f.write(f"总切换次数: {len(all_switch_events)}\\n")
                f.write(f"平均切换耗时: {avg_cost:.0f}ms\\n")
                f.write(f"最快切换: {min(all_costs)}ms\\n")
                f.write(f"最慢切换: {max(all_costs)}ms\\n")
                f.write("\\n详细切换事件:\\n")
                f.write("-" * 50 + "\\n")
                for event in all_switch_events:
                    f.write(f"{event['timestamp']}: {event['old_master']} → {event['new_master']} ({event['cost_ms']}ms)\\n")
                f.write("\\n")

            f.write("4. 存储一致性统计\\n")
            f.write("-" * 50 + "\\n")
            f.write(f"Redis: {redis_stats['正常']}/{success_count} 正常, {redis_stats['异常']} 异常, {redis_stats['检查失败']} 检查失败\\n")
            f.write(f"ES: {es_stats['正常']}/{success_count} 正常, {es_stats['异常']} 异常, {es_stats['检查失败']} 检查失败\\n")
            f.write(f"DM: {dm_stats['正常']}/{success_count} 正常, {dm_stats['异常']} 异常, {dm_stats['检查失败']} 检查失败\\n\\n")

        self.logger.success(f"详细报告已保存: {report_file}")


def main():
    """主函数"""
    tester = HighAvailabilityClusterTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()'''

if old_code not in content:
    print("ERROR: 未找到截断代码，文件可能已被修改")
    sys.exit(1)

content = content.replace(old_code, new_code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("修复完成")
