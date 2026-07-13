"""验证第二轮架构优化后的导入"""
import sys, os
_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utm_simulator')
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, '..', 'database'))
sys.path.insert(0, os.path.join(_root, '..', 'common'))

from web_server import app
print('web_server OK:', app.name)

from sim_manager import SimulationManager
print('sim_manager OK')

from db_manager import query_all, init_tables
print('db_manager OK')

from config import load_config
print('config OK')

from exceptions import UTMSimulationError
print('exceptions OK')

from log_setup import get_logger
print('log_setup OK')

from log_streamer import get_streamer
print('log_streamer OK')

from validators import validate_scenario
print('validators OK')

from schemas import DroneRouteDict
print('schemas OK')

print('ALL IMPORTS PASSED')
