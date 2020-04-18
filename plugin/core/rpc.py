from .logging import debug, exception_log
from .protocol import Request, Notification, Response, Error, ErrorCode
from .transports import create_transport, JsonRpcTransport, TransportCallbacks
from .types import ClientConfig, Settings
from .typing import Any, Dict, Tuple, Callable, Optional, Mapping
from threading import Condition
from threading import Lock
import sublime

TCP_CONNECT_TIMEOUT = 5
DEFAULT_SYNC_REQUEST_TIMEOUT = 1.0


class PreformattedPayloadLogger:

    def __init__(self, settings: Settings, server_name: str, sink: Callable[[str], None]) -> None:
        self.settings = settings
        self.server_name = server_name
        self.sink = sink

    def log(self, message: str, params: Any, log_payload: bool) -> None:
        if log_payload:
            message = "{}: {}".format(message, params)
        self.sink(message)

    def format_response(self, direction: str, request_id: Any) -> str:
        return "{} {} {}".format(direction, self.server_name, request_id)

    def format_request(self, direction: str, method: str, request_id: Any) -> str:
        return "{} {} {}({})".format(direction, self.server_name, method, request_id)

    def format_notification(self, direction: str, method: str) -> str:
        return "{} {} {}".format(direction, self.server_name, method)

    def outgoing_response(self, request_id: Any, params: Any) -> None:
        if not self.settings.log_debug:
            return
        self.log(self.format_response(">>>", request_id), params, self.settings.log_payloads)

    def outgoing_error_response(self, request_id: Any, error: Error) -> None:
        if not self.settings.log_debug:
            return
        self.log(self.format_response("~~>", request_id), error.to_lsp(), self.settings.log_payloads)

    def outgoing_request(self, request_id: int, method: str, params: Any, blocking: bool) -> None:
        if not self.settings.log_debug:
            return
        direction = "==>" if blocking else "-->"
        self.log(self.format_request(direction, method, request_id), params, self.settings.log_payloads)

    def outgoing_notification(self, method: str, params: Any) -> None:
        if not self.settings.log_debug:
            return
        # Do not log the payloads if any of these conditions occur because the payloads might contain the entire
        # content of the view.
        log_payload = self.settings.log_payloads
        if method.endswith("didOpen"):
            log_payload = False
        elif method.endswith("didChange"):
            content_changes = params.get("contentChanges")
            if content_changes and "range" not in content_changes[0]:
                log_payload = False
        elif method.endswith("didSave"):
            if isinstance(params, dict) and "text" in params:
                log_payload = False
        self.log(self.format_notification(" ->", method), params, log_payload)

    def incoming_response(self, request_id: int, params: Any) -> None:
        if not self.settings.log_debug:
            return
        self.log(self.format_response("<<<", request_id), params, self.settings.log_payloads)

    def incoming_error_response(self, request_id: Any, error: Any) -> None:
        if not self.settings.log_debug:
            return
        self.log(self.format_response('<~~', request_id), error, self.settings.log_payloads)

    def incoming_request(self, request_id: Any, method: str, params: Any) -> None:
        if not self.settings.log_debug:
            return
        self.log(self.format_request("<--", method, request_id), params, self.settings.log_payloads)

    def incoming_notification(self, method: str, params: Any, unhandled: bool) -> None:
        if not self.settings.log_debug or method == "window/logMessage":
            return
        direction = "<? " if unhandled else "<- "
        self.log(self.format_notification(direction, method), params, self.settings.log_payloads)


class Client(TransportCallbacks):
    def __init__(self, config: ClientConfig, cwd: str, window: sublime.Window, settings: Settings) -> None:
        self.transport = create_transport(config, cwd, window, self)  # type: Optional[JsonRpcTransport]
        self.request_id = 0  # Our request IDs are always integers.
        self.logger = PreformattedPayloadLogger(settings, config.name, debug)
        self._response_handlers = {}  # type: Dict[int, Tuple[Optional[Callable], Optional[Callable[[Any], None]]]]
        self._sync_request_results = {}  # type: Dict[int, Optional[Any]]
        self._sync_request_lock = Lock()
        self._sync_request_cvar = Condition(self._sync_request_lock)
        self.exiting = False

    def send_request(
            self,
            request: Request,
            handler: Callable[[Optional[Any]], None],
            error_handler: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self.request_id += 1
        self.logger.outgoing_request(self.request_id, request.method, request.params, blocking=False)
        self._response_handlers[self.request_id] = (handler, error_handler)
        self.send_payload(request.to_payload(self.request_id))

    def execute_request(self, request: Request, timeout: float = DEFAULT_SYNC_REQUEST_TIMEOUT) -> Optional[Any]:
        """
        Sends a request and waits for response up to timeout (default: 1 second), blocking the current thread.
        """
        self.request_id += 1
        request_id = self.request_id
        self.logger.outgoing_request(request_id, request.method, request.params, blocking=True)
        self.send_payload(request.to_payload(request_id))
        result = None
        try:
            with self._sync_request_cvar:
                # We go to sleep. We wake up once another thread calls .notify() on this condition variable.
                self._sync_request_cvar.wait_for(lambda: request_id in self._sync_request_results, timeout)
                result = self._sync_request_results.pop(request_id)
        except KeyError:
            debug('timeout on', request.method)
            return None
        return result

    def send_notification(self, notification: Notification) -> None:
        self.logger.outgoing_notification(notification.method, notification.params)
        self.send_payload(notification.to_payload())

    def send_response(self, response: Response) -> None:
        self.logger.outgoing_response(response.request_id, response.result)
        self.send_payload(response.to_payload())

    def send_error_response(self, request_id: Any, error: Error) -> None:
        self.logger.outgoing_error_response(request_id, error)
        self.send_payload({'jsonrpc': '2.0', 'id': request_id, 'error': error.to_lsp()})

    def exit(self) -> None:
        self.exiting = True
        self.send_notification(Notification.exit())
        try:
            self.transport.close()  # type: ignore
        except AttributeError:
            pass

    def send_payload(self, payload: Dict[str, Any]) -> None:
        try:
            self.transport.send(payload)  # type: ignore
        except AttributeError:
            pass

    def on_payload(self, payload: Dict[str, Any]) -> None:
        if "method" in payload:
            self.request_or_notification_handler(payload)
        elif "id" in payload:
            self.response_handler(payload)
        else:
            debug("Unknown payload type: ", payload)

    def on_stderr_message(self, message: str) -> None:
        pass

    def on_transport_close(self, exit_code: int, exception: Optional[Exception]) -> None:
        self.transport = None

    def response_handler(self, response: Dict[str, Any]) -> None:
        # This response handler *must not* run from the same thread that does a sync request
        # because of the usage of the condition variable below.
        request_id = int(response["id"])
        handler, error_handler = self._response_handlers.pop(request_id, (None, None))
        if "result" in response and "error" not in response:
            result = response["result"]
            self.logger.incoming_response(request_id, result)
            if handler:
                handler(result)
            else:
                with self._sync_request_cvar:
                    self._sync_request_results[request_id] = result
                    # At most one thread is waiting on the result.
                    self._sync_request_cvar.notify()
        elif "result" not in response and "error" in response:
            error = response["error"]
            self.logger.incoming_error_response(request_id, error)
            if error_handler:
                error_handler(error)
            else:
                raise Error(error["code"], error["message"], error.get("data"))
        else:
            debug('invalid response payload', response)

    def request_or_notification_handler(self, payload: Mapping[str, Any]) -> None:
        method = payload["method"]  # type: str
        handler = getattr(self, 'm_{}'.format(method.replace('/', '_').replace('$', '_')), None)
        params = payload.get("params")
        # Server request IDs can be either a string or an int.
        request_id = payload.get("id")
        if request_id is not None:
            self.logger.incoming_request(request_id, method, params)
            if callable(handler):
                try:
                    handler(params, request_id)
                except Error as error:
                    # The request handler raised this exception on purpose, so don't log this exception.
                    self.send_error_response(request_id, error)
                except Exception as ex:
                    # The request handler didn't raise this exception on purpose, so log the exception.
                    exception_log("Error handling request {}".format(method), ex)
                    self.send_error_response(request_id, Error.from_exception(ex))
            else:
                self.send_error_response(request_id, Error(ErrorCode.MethodNotFound, method))
        else:
            if callable(handler):
                try:
                    handler(params)
                    self.logger.incoming_notification(method, params, unhandled=False)
                except Exception as err:
                    exception_log("Error handling notification {}".format(method), err)
                    self.logger.incoming_notification(method, params, unhandled=True)
            else:
                self.logger.incoming_notification(method, params, unhandled=True)
