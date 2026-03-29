"""异常定义模块"""


class AppException(Exception):
    """应用异常基类"""
    def __init__(self, code: int, message: str, data: dict = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(self.message)


class DataNotFoundError(AppException):
    """数据未找到"""
    def __init__(self, message: str = "数据未找到"):
        super().__init__(code=404, message=message)


class DataCollectError(AppException):
    """数据采集失败"""
    def __init__(self, message: str = "数据采集失败"):
        super().__init__(code=500, message=message)


class ExternalAPIError(AppException):
    """外部API调用失败"""
    def __init__(self, source: str, message: str):
        super().__init__(code=503, message=f"{source} API调用失败: {message}")


class ValidationError(AppException):
    """参数验证失败"""
    def __init__(self, message: str = "参数验证失败"):
        super().__init__(code=400, message=message)


class DatabaseError(AppException):
    """数据库操作失败"""
    def __init__(self, message: str = "数据库操作失败"):
        super().__init__(code=500, message=message)
