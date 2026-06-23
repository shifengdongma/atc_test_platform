import requests
import urllib3
from Jwt_Token_get import get_jwt_token

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def search_flight_task(
    keyword: str = "",
    task_status: str = "",
    task_purpose: str = "",
    task_type: str = "",
    start_time: int = 0,
    end_time: int = 0,
    page_no: int = 0,
    page_size: int = 10,
    sort_field: str = "startTime",
    sort_direction: str = "desc",
    base_url: str = "https://dkkgsit-test.testdolphin.com",
) -> dict:
    """
    飞行任务列表查询

    POST /la-atc-biz-backend/flight/task/search

    Args:
        keyword: 关键字(任务名称|任务编号)
        task_status: 任务状态，字典(FLIGHT_TASK_STATUS)
        task_purpose: 任务目的，字典(TASK_PURPOSE)
        task_type: 任务性质，字典(TASK_TYPE)
        start_time: 任务开始时段(时间戳)
        end_time: 任务结束时段(时间戳)
        page_no: 页码，从0开始
        page_size: 每页条数
        sort_field: 排序字段(taskStatus|startTime)
        sort_direction: 排序方向(asc|desc)
        base_url: 服务基础地址

    Returns:
        接口响应 JSON 字典
    """
    url = f"{base_url}/la-atc-biz-backend/flight/task/search"
    token = get_jwt_token(base_url=base_url)

    headers = {
        "Content-Type": "application/json",
        "jwt-token": token,
    }

    body = {
        "keyword": keyword,
        "taskStatus": task_status,
        "taskPurpose": task_purpose,
        "taskType": task_type,
        "startTime": start_time,
        "endTime": end_time,
        "pageNo": page_no,
        "pageSize": page_size,
        "sortField": sort_field,
        "sortDirection": sort_direction,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, verify=False, timeout=30)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    result = search_flight_task(page_size=5)
    print(result)
