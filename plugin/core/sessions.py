from .logging import debug
from .protocol import completion_item_kinds, symbol_kinds, WorkspaceFolder, Request, Notification, Response
from .protocol import TextDocumentSyncKindNone
from .rpc import Client
from .types import ClientConfig, ClientStates, Settings
from .typing import Dict, Any, Optional, List, Tuple
from .workspace import is_subpath_of, get_workspace_folders
import weakref
import os


def get_initialize_params(workspace_folders: List[WorkspaceFolder], config: ClientConfig) -> dict:
    first_folder = workspace_folders[0] if workspace_folders else None
    initializeParams = {
        "processId": os.getpid(),
        "clientInfo": {
            "name": "Sublime Text LSP",
        },
        "rootUri": first_folder.uri() if first_folder else None,
        "rootPath": first_folder.path if first_folder else None,
        "workspaceFolders": [folder.to_lsp() for folder in workspace_folders] if workspace_folders else None,
        "capabilities": {
            "textDocument": {
                "synchronization": {
                    "didSave": True,
                    "willSave": True,
                    "willSaveWaitUntil": True
                },
                "hover": {
                    "contentFormat": ["markdown", "plaintext"]
                },
                "completion": {
                    "completionItem": {
                        "snippetSupport": True,
                        "deprecatedSupport": True
                    },
                    "completionItemKind": {
                        "valueSet": completion_item_kinds
                    }
                },
                "signatureHelp": {
                    "signatureInformation": {
                        "documentationFormat": ["markdown", "plaintext"],
                        "parameterInformation": {
                            "labelOffsetSupport": True
                        }
                    }
                },
                "references": {},
                "documentHighlight": {},
                "documentSymbol": {
                    "symbolKind": {
                        "valueSet": symbol_kinds
                    }
                },
                "formatting": {},
                "rangeFormatting": {},
                "declaration": {"linkSupport": True},
                "definition": {"linkSupport": True},
                "typeDefinition": {"linkSupport": True},
                "implementation": {"linkSupport": True},
                "codeAction": {
                    "codeActionLiteralSupport": {
                        "codeActionKind": {
                            "valueSet": []
                        }
                    }
                },
                "rename": {},
                "colorProvider": {},
                "publishDiagnostics": {
                    "relatedInformation": True
                }
            },
            "workspace": {
                "applyEdit": True,
                "didChangeConfiguration": {},
                "executeCommand": {},
                "workspaceFolders": True,
                "symbol": {
                    "symbolKind": {
                        "valueSet": symbol_kinds
                    }
                },
                "configuration": True
            }
        }
    }
    if config.init_options is not None:
        initializeParams['initializationOptions'] = config.init_options

    return initializeParams


def diff_folders(old: List[WorkspaceFolder],
                 new: List[WorkspaceFolder]) -> Tuple[List[WorkspaceFolder], List[WorkspaceFolder]]:
    added = []  # type: List[WorkspaceFolder]
    removed = []  # type: List[WorkspaceFolder]
    for folder in old:
        if folder not in new:
            removed.append(folder)
    for folder in new:
        if folder not in old:
            added.append(folder)
    return added, removed


def get_dotted_value(current: Any, dotted: str) -> Any:
    keys = dotted.split('.')
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


class Session(Client):
    def __init__(self, window_manager: Any, settings: Settings, cwd: str, config: ClientConfig) -> None:
        self.config = config
        self.manager = weakref.ref(window_manager)
        self.state = ClientStates.STARTING
        self.capabilities = dict()  # type: Dict[str, Any]
        self._workspace_folders = get_workspace_folders(window_manager._workspace.folders)
        super().__init__(config, cwd, window_manager._window, settings)

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities and self.capabilities[capability] is not False

    def get_capability(self, capability: str) -> Optional[Any]:
        return self.capabilities.get(capability)

    def should_notify_did_open(self) -> bool:
        textsync = self.capabilities.get('textDocumentSync')
        if isinstance(textsync, dict):
            return bool(textsync.get('openClose'))
        if isinstance(textsync, int):
            return textsync > TextDocumentSyncKindNone
        return False

    def text_sync_kind(self) -> int:
        textsync = self.capabilities.get('textDocumentSync')
        if isinstance(textsync, dict):
            return int(textsync.get('change', TextDocumentSyncKindNone))
        if isinstance(textsync, int):
            return textsync
        return TextDocumentSyncKindNone

    def should_notify_did_change(self) -> bool:
        return self.text_sync_kind() > TextDocumentSyncKindNone

    def should_notify_will_save(self) -> bool:
        textsync = self.capabilities.get('textDocumentSync')
        if isinstance(textsync, dict):
            return bool(textsync.get('willSave'))
        return False

    def should_request_will_save_wait_until(self) -> bool:
        textsync = self.capabilities.get('textDocumentSync')
        if isinstance(textsync, dict):
            return bool(textsync.get('willSaveWaitUntil'))
        return False

    def should_notify_did_save(self) -> Tuple[bool, bool]:
        textsync = self.capabilities.get('textDocumentSync')
        if isinstance(textsync, dict):
            options = textsync.get('save')
            if isinstance(options, dict):
                return True, bool(options.get('includeText'))
            elif isinstance(options, bool):
                return options, False
        return False, False

    def should_notify_did_close(self) -> bool:
        return self.should_notify_did_open()

    def handles_path(self, file_path: Optional[str]) -> bool:
        if not file_path:
            return False

        if not self._workspace_folders:
            return True

        for folder in self._workspace_folders:
            if is_subpath_of(file_path, folder.path):
                return True

        return False

    def update_folders(self, folders: List[WorkspaceFolder]) -> None:
        if self._supports_workspace_folders():
            added, removed = diff_folders(self._workspace_folders, folders)
            params = {
                "event": {
                    "added": [a.to_lsp() for a in added],
                    "removed": [r.to_lsp() for r in removed]
                }
            }
            notification = Notification.didChangeWorkspaceFolders(params)
            self.send_notification(notification)
            self._workspace_folders = folders

    def initialize(self) -> None:
        params = get_initialize_params(self._workspace_folders, self.config)
        self.send_request(Request.initialize(params), self._handle_initialize_result, lambda _: self.end())

    def call_manager(self, method: str, *args: Any) -> None:
        mgr = self.manager()
        if mgr:
            getattr(mgr, method)(*args)

    def on_stderr_message(self, message: str) -> None:
        self.call_manager('handle_stderr_log', self, message)

    def _supports_workspace_folders(self) -> bool:
        workspace_cap = self.capabilities.get("workspace", {})
        workspace_folder_cap = workspace_cap.get("workspaceFolders", {})
        return workspace_folder_cap.get("supported")

    def _handle_initialize_result(self, result: Any) -> None:
        self.capabilities.update(result.get('capabilities', dict()))

        # only keep supported amount of folders
        if self._workspace_folders:
            if self._supports_workspace_folders():
                debug('multi folder session:', self._workspace_folders)
            else:
                self._workspace_folders = self._workspace_folders[:1]
                debug('single folder session:', self._workspace_folders[0])
        else:
            debug("session with no workspace folders")

        self.state = ClientStates.READY

        if self.config.settings:
            self.send_notification(Notification.didChangeConfiguration({'settings': self.config.settings}))

        self.call_manager('on_post_initialize', self)

    def m_window_showMessageRequest(self, params: Any, request_id: Any) -> None:
        """handles the window/showMessageRequest request"""
        self.call_manager('handle_message_request', self, params, request_id)

    def m_window_showMessage(self, params: Any) -> None:
        """handles the window/showMessage notification"""
        self.call_manager('handle_show_message', self, params)

    def m_window_logMessage(self, params: Any) -> None:
        """handles the window/logMessage notification"""
        self.call_manager('handle_log_message', self, params)

    def m_workspace_workspaceFolders(self, _: Any, request_id: Any) -> None:
        """handles the workspace/workspaceFolders request"""
        self.send_response(Response(request_id, [wf.to_lsp() for wf in self._workspace_folders]))

    def m_workspace_configuration(self, params: Dict[str, Any], request_id: Any) -> None:
        """handles the workspace/configuration request"""
        items = []  # type: List[Any]
        requested_items = params.get("items") or []
        for requested_item in requested_items:
            if 'section' in requested_item:
                section = requested_item['section']
                if section:
                    items.append(get_dotted_value(self.config.settings, section))
                else:
                    items.append(self.config.settings)
            else:
                items.append(self.config.settings)
        self.send_response(Response(request_id, items))

    def m_workspace_applyEdit(self, params: Any, request_id: Any) -> None:
        """handles the workspace/applyEdit request"""
        self.call_manager('_apply_workspace_edit', self, params, request_id)

    def m_textDocument_publishDiagnostics(self, params: Any) -> None:
        """handles textDocument/publishDiagnostics notification"""
        mgr = self.manager()
        if mgr:
            mgr.diagnostics.receive(self.config.name, params)

    def end(self) -> None:
        debug("stopping", self.config.name, "gracefully")
        self.capabilities.clear()
        self.state = ClientStates.STOPPING
        self.send_request(Request.shutdown(), self._handle_shutdown_result, self._handle_shutdown_result)

    def _handle_shutdown_result(self, _: Any) -> None:
        self.send_notification(Notification.exit())

    def on_transport_close(self, exit_code: int, exception: Optional[Exception]) -> None:
        super().on_transport_close(exit_code, exception)
        debug("stopped", self.config.name, "exit code", exit_code)
        self.call_manager('on_post_exit', self, exit_code, exception)


def create_session(window_manager: Any, settings: Settings, cwd: str, config: ClientConfig) -> Session:
    return Session(window_manager, settings, cwd, config)
