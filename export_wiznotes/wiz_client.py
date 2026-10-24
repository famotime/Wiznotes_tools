"""
为知笔记客户端核心类
包含登录、获取文件夹、获取笔记列表、下载笔记等基础API操作
支持多线程并发与 Token 失效（401/Invalid）自动重新登录与无感重试
"""

import json
import logging
import threading
from pathlib import Path
from dotenv import dotenv_values
import requests


class WizNoteClient:
    AS_URL = 'https://as.wiz.cn'
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent

    def __init__(self, config_path=None, server_url=None):
        self.config = self._load_config(config_path)
        # 支持自建服务器：优先使用传入的 server_url，其次从配置读取，最后默认官方 https://as.wiz.cn
        configured_url = server_url or self.config.get('wiz', {}).get('server_url') or self.AS_URL
        self.server_url = str(configured_url).rstrip('/')
        self.token = None
        self.kb_info = None
        self._token_lock = threading.Lock()

    def _load_config(self, config_path=None):
        """加载配置：优先从 .env 文件读取，其次从 JSON 配置文件读取"""
        # 优先尝试 .env
        env_path = self._PROJECT_ROOT / ".env"
        if env_path.exists():
            env = dotenv_values(env_path)
            username = env.get("WIZ_USERNAME", "")
            password = env.get("WIZ_PASSWORD", "")
            server_url = env.get("WIZ_SERVER_URL", "")
            if username and password:
                logging.info(f"从 .env 文件加载配置: {env_path}")
                wiz_cfg = {"username": username, "password": password}
                if server_url:
                    wiz_cfg["server_url"] = server_url
                return {"wiz": wiz_cfg}
            logging.warning(".env 文件存在但缺少 WIZ_USERNAME 或 WIZ_PASSWORD")

        # 后备：JSON 配置文件
        if config_path:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    logging.info(f"从 JSON 配置文件加载: {config_path}")
                    return json.load(f)
            except Exception as e:
                logging.error(f"加载配置文件失败: {e}")
                raise

        raise FileNotFoundError(
            f"未找到配置文件。请在项目根目录创建 .env 文件（参考 .env.example）"
        )

    def _is_token_invalid_response(self, response, result_dict=None):
        """检查 HTTP 响应或 API 报文是否表示 Token 已失效"""
        if response.status_code in (401, 403):
            return True
        if result_dict and isinstance(result_dict, dict):
            return_code = result_dict.get('returnCode')
            return_msg = str(result_dict.get('returnMessage', '')).lower()
            if return_code in (301, 401, 403) or 'token' in return_msg:
                if any(k in return_msg for k in ['invalid', 'expired', 'expire', '过期', '无效', '重新登录', '未登录']):
                    return True
        return False

    def _refresh_token_safe(self, old_token):
        """线程安全地重新登录以刷新 Token"""
        with self._token_lock:
            # 双重检查：如果其他并发线程已刷新过 Token，直接复用最新 Token
            if self.token and self.token != old_token:
                return self.token
            logging.warning("检测到为知笔记 Token 失效或过期，正在自动重新登录刷新...")
            self.login()
            logging.info("为知笔记 Token 自动刷新成功！")
            return self.token

    def _http_request(self, method, url, headers=None, auto_retry=True, **kwargs):
        """底层 HTTP 请求，自动附带 X-Wiz-Token 并支持 Token 失效自动重新登录与重试"""
        current_token = self.token
        max_attempts = 2 if (auto_retry and current_token) else 1

        for attempt in range(max_attempts):
            req_headers = dict(headers or {})
            if current_token:
                req_headers['X-Wiz-Token'] = current_token

            response = requests.request(method=method, url=url, headers=req_headers, **kwargs)

            # 首次失败且启用自动重试时，检测是否为 Token 失效
            if auto_retry and current_token and attempt == 0:
                is_invalid = False
                if response.status_code in (401, 403):
                    is_invalid = True
                elif response.headers.get('Content-Type', '').startswith('application/json') or (response.text and response.text.startswith('{')):
                    try:
                        res_json = response.json()
                        if self._is_token_invalid_response(response, res_json):
                            is_invalid = True
                    except Exception:
                        pass

                if is_invalid:
                    current_token = self._refresh_token_safe(current_token)
                    continue

            return response

    def _request(self, method, url, data=None, token=None, headers=None):
        """统一 JSON API 请求处理，支持 Token 失效自动重试"""
        is_login_req = '/as/user/login' in url
        try:
            if is_login_req:
                response = requests.request(
                    method=method,
                    url=url,
                    json=data if data else None,
                    headers=headers
                )
            else:
                response = self._http_request(
                    method=method,
                    url=url,
                    json=data if data else None,
                    headers=headers,
                    auto_retry=True
                )

            # 检查返回内容是否为空
            if not response.text or not response.text.strip():
                logging.error(f"请求返回空内容: {url}")
                return None

            result = response.json()
            if result.get('returnCode') != 200:
                ret_code = result.get('returnCode')
                ret_msg = result.get('returnMessage') or '未知错误'
                extern_code = result.get('externCode')
                err_detail = f"API错误 (code: {ret_code}): {ret_msg}"
                if extern_code:
                    err_detail += f" [externCode: {extern_code}]"
                raise Exception(err_detail)

            return result.get('result')

        except Exception as e:
            logging.error(f"请求失败: {e}")
            raise

    def login(self):
        """登录获取token，支持自建服务器与友好故障诊断"""
        try:
            data = {
                'userId': self.config['wiz']['username'],
                'password': self.config['wiz']['password']
            }

            logging.info(f"正在连接为知笔记服务器: {self.server_url}")
            result = self._request('POST', f"{self.server_url}/as/user/login", data)
            self.token = result['token']
            self.kb_info = {
                'kbServer': result['kbServer'],
                'kbGuid': result['kbGuid'],
                'userGuid': result.get('userGuid', '')  # 添加userGuid
            }
            logging.info("登录成功")
            return result

        except Exception as e:
            err_str = str(e)
            hint_lines = []
            if any(k in err_str.lower() for k in ["invalidpassword", "密码错误", "401", "403"]):
                hint_lines.append("  • 请核对用户名与密码是否正确。若密码中包含特殊字符（如 #、$、空格），请在 .env 中用双引号包裹。")
            if any(k in err_str.lower() for k in ["token", "验证", "api错误"]):
                hint_lines.append("  • 若账户开启了「二次登录验证（两步验证）」，Web API 会拒绝登录，请先在官方客户端中暂时关闭二次验证后再导出。")
            if any(k in err_str.lower() for k in ["connection", "timeout", "refused", "name or service not known"]):
                hint_lines.append(f"  • 无法连接服务器 ({self.server_url})。如使用自建服务器，请确认 WIZ_SERVER_URL 及网络端口正常开放。")

            if hint_lines:
                suggestions = "\n".join(hint_lines)
                logging.error(f"登录失败: {e}\n[常见排查建议]:\n{suggestions}")
            else:
                logging.error(f"登录失败: {e}")
            raise

    def get_folders(self):
        """获取笔记文件夹列表"""
        try:
            url = f"{self.kb_info['kbServer']}/ks/category/all/{self.kb_info['kbGuid']}"
            return self._request('GET', url)
        except Exception as e:
            logging.error(f"获取文件夹列表失败: {e}")
            raise

    def get_note_list(self, folder, count=100, max_notes=None):
        """获取指定文件夹下的笔记列表

        Args:
            folder: 文件夹路径
            count: 每页笔记数量，默认100
            max_notes: 最大获取笔记数量，如果超过1000则会自动进行两次查询
        """
        try:
            note_list = []
            seen_guids = set()  # 用于去重的GUID集合

            # 如果max_notes大于1000，需要进行两次查询
            if max_notes and max_notes > 1000:
                # 第一次查询：降序获取前1000条
                logging.info(f"文件夹笔记数超过1000 ({max_notes})，使用双向查询...")
                desc_notes = self._get_notes_by_order(folder, count, order="desc")
                for note in desc_notes:
                    if note['docGuid'] not in seen_guids:
                        seen_guids.add(note['docGuid'])
                        note_list.append(note)

                # 第二次查询：升序获取前1000条
                asc_notes = self._get_notes_by_order(folder, count, order="asc")
                new_notes_count = 0
                for note in asc_notes:
                    if note['docGuid'] not in seen_guids:
                        seen_guids.add(note['docGuid'])
                        note_list.append(note)
                        new_notes_count += 1

                logging.info(f"双向查询完成: 降序获取 {len(desc_notes)} 篇，升序补充 {new_notes_count} 篇，去重后共 {len(note_list)} 篇")
                return note_list
            else:
                # 正常查询：笔记数小于等于1000或者没有指定max_notes
                return self._get_notes_by_order(folder, count, order="desc")

        except Exception as e:
            logging.error(f"获取笔记列表失败: {e}")
            raise

    def _get_notes_by_order(self, folder, count=100, order="desc"):
        """按指定顺序获取笔记列表

        Args:
            folder: 文件夹路径
            count: 每页笔记数量
            order: 排序顺序，"asc"为升序，"desc"为降序
        """
        notes = []
        start = 0

        while True:
            # 注意：order参数已经是"asc"或"desc"，直接使用
            url = (f"{self.kb_info['kbServer']}/ks/note/list/category/{self.kb_info['kbGuid']}"
                  f"?start={start}&count={count}&category={folder}"
                  f"&orderBy=modified&ascending={order}")

            sub_notes = self._request('GET', url)
            if not sub_notes:
                break

            notes.extend(sub_notes)

            if len(sub_notes) < count:
                break

            start += count

        return notes

    def download_note(self, doc_guid):
        """下载指定笔记内容"""
        try:
            # 使用download接口获取笔记详情，这个接口会返回笔记类型
            url = (f"{self.kb_info['kbServer']}/ks/note/download/{self.kb_info['kbGuid']}/{doc_guid}"
                  "?downloadInfo=1&downloadData=1")
            response = self._http_request('GET', url)

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            try:
                result = json.loads(response.content.decode('utf-8'))
                logging.debug(f"笔记下载响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            except json.JSONDecodeError:
                logging.error("JSON解析失败，返回内容：")
                logging.error(response.content)
                raise

            if result.get('returnCode') != 200:
                raise Exception(f"API错误: {result.get('returnMessage')}")

            # 从result中获取笔记信息和类型
            note_info = result.get('info', {})
            html_content = result.get('html', '')
            resources = result.get('resources', [])
            note_type = note_info.get('type', 'document')  # 从info中获取type字段

            logging.info(f"笔记类型: {note_type}, 笔记标题: {note_info.get('title', 'Unknown')}")

            # 如果是协作笔记，使用WebSocket获取数据
            if note_type == 'collaboration':
                try:
                    # 获取协作笔记token
                    token_url = f"{self.kb_info['kbServer']}/ks/note/{self.kb_info['kbGuid']}/{doc_guid}/tokens"
                    token_response = self._http_request('POST', token_url)

                    if token_response.status_code != 200:
                        raise Exception(f"获取协作笔记token失败: {token_response.status_code}")

                    token_result = token_response.json()
                    if token_result.get('returnCode') != 200:
                        raise Exception(f"获取协作笔记token失败: {token_result.get('returnMessage')}")

                    editor_token = token_result['result']['editorToken']

                    # 使用WebSocket获取协作笔记内容
                    try:
                        from .collaboration_parser import CollaborationParser
                    except ImportError:
                        from collaboration_parser import CollaborationParser

                    parser = CollaborationParser(self.kb_info)
                    collaboration_content = parser.get_collaboration_content(editor_token, doc_guid)

                    # 解析协作笔记内容为Markdown
                    markdown_content = parser.parse_collaboration_content(collaboration_content)

                    return {
                        'info': note_info,
                        'html': markdown_content,
                        'resources': resources,
                        'type': 'collaboration',
                        'editor_token': editor_token
                    }

                except Exception as e:
                    logging.error(f"处理协作笔记失败: {e}")
                    # 如果协作笔记处理失败，回退到普通笔记处理
                    logging.info("回退到普通笔记处理方式")

            # 处理普通笔记或协作笔记处理失败的情况
            if resources:
                for resource in resources:
                    logging.debug(f"资源文件: {resource.get('name')} ({resource.get('size')} bytes)")

            return {
                'info': note_info,
                'html': html_content,
                'resources': resources,
                'type': note_type
            }

        except Exception as e:
            logging.error(f"下载笔记失败: {e}")
            raise

    def download_resource(self, doc_guid, resource_info, save_path):
        """下载笔记资源文件"""
        try:
            # 使用资源信息中的URL直接下载
            url = resource_info.get('url')
            if not url:
                logging.error(f"资源文件缺少URL: {resource_info}")
                return False

            logging.debug(f"开始下载资源: {url}")
            response = self._http_request('GET', url)

            if response.status_code == 200:
                # 确保父目录存在
                save_path.parent.mkdir(parents=True, exist_ok=True)

                with open(save_path, 'wb') as f:
                    f.write(response.content)
                return True
            else:
                logging.error(f"资源下载失败 ({response.status_code}): {url}")
                return False

        except Exception as e:
            logging.error(f"下载资源失败: {e}")
            return False

    def get_note_attachments(self, doc_guid):
        """获取笔记的附件列表"""
        try:
            url = f"{self.kb_info['kbServer']}/ks/note/attachments/{self.kb_info['kbGuid']}/{doc_guid}"
            response = self._http_request('GET', url)

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            result = response.json()
            if result.get('returnCode') != 200:
                ret_code = result.get('returnCode')
                ret_msg = result.get('returnMessage') or '未知错误'
                extern_code = result.get('externCode')
                err_detail = f"API错误 (code: {ret_code}): {ret_msg}"
                if extern_code:
                    err_detail += f" [externCode: {extern_code}]"
                raise Exception(err_detail)

            attachments = result.get('result', [])
            logging.debug(f"笔记附件列表: {json.dumps(attachments, ensure_ascii=False, indent=2)}")
            return attachments

        except Exception as e:
            logging.error(f"获取笔记附件列表失败: {e}")
            return []

    def get_attachment_history(self, doc_guid, att_guid):
        """获取附件的历史版本列表"""
        try:
            url = (f"{self.kb_info['kbServer']}/ks/history/list/{self.kb_info['kbGuid']}/{doc_guid}"
                  f"?objType=attachment&objGuid={att_guid}")
            response = self._http_request('GET', url)

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            result = response.json()
            if result.get('returnCode') != 200:
                ret_code = result.get('returnCode')
                ret_msg = result.get('returnMessage') or '未知错误'
                extern_code = result.get('externCode')
                err_detail = f"API错误 (code: {ret_code}): {ret_msg}"
                if extern_code:
                    err_detail += f" [externCode: {extern_code}]"
                raise Exception(err_detail)

            history = result.get('history', [])
            logging.debug(f"附件历史版本: {json.dumps(history, ensure_ascii=False, indent=2)}")
            return history

        except Exception as e:
            logging.error(f"获取附件历史版本失败: {e}")
            return []

    def download_attachment(self, doc_guid, att_guid, save_path):
        """下载附件"""
        try:
            url = (f"{self.kb_info['kbServer']}/ks/attachment/download/"
                   f"{self.kb_info['kbGuid']}/{doc_guid}/{att_guid}")
            response = self._http_request('GET', url)

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            # 检查返回类型，避免写入json错误信息
            if response.headers.get('Content-Type', '').startswith('application/json'):
                logging.error(f"下载附件失败，返回内容: {response.text}")
                return False

            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(response.content)

            logging.info(f"成功下载附件: {save_path}")
            return True

        except Exception as e:
            logging.error(f"下载附件失败: {e}")
            return False

    def get_all_tags(self):
        """获取所有标签，返回tagId到标签名的映射字典"""
        try:
            url = f"{self.kb_info['kbServer']}/ks/tag/all/{self.kb_info['kbGuid']}"
            response = self._http_request('GET', url)
            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")
            result = response.json()
            if result.get('returnCode') != 200:
                ret_code = result.get('returnCode')
                ret_msg = result.get('returnMessage') or '未知错误'
                extern_code = result.get('externCode')
                err_detail = f"API错误 (code: {ret_code}): {ret_msg}"
                if extern_code:
                    err_detail += f" [externCode: {extern_code}]"
                raise Exception(err_detail)
            tags = result.get('result', [])
            tag_map = {tag['tagGuid']: tag['name'] for tag in tags}
            return tag_map
        except Exception as e:
            logging.error(f"获取标签列表失败: {e}")
            return {}
