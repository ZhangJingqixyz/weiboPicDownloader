# -*- coding: utf-8 -*-

from functools import reduce
import sys, locale, platform
import time, os, json, re, datetime, math, operator
import concurrent.futures
import requests
import argparse
try:
    # Py3
    from urllib.parse import quote
except Exception:
    # Py2 fallback
    from urllib import quote

try:
    reload(sys)
    sys.setdefaultencoding('utf8')
except:
    pass

is_python2 = sys.version[0] == '2'
system_encoding = sys.stdin.encoding or locale.getpreferredencoding(True)

if platform.system() == 'Windows':
    if operator.ge(*map(lambda version: list(map(int, version.split('.'))), [platform.version(), '10.0.14393'])):
        os.system('')
    else:
        import colorama
        colorama.init()

try:
    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
except:
    pass

parser = argparse.ArgumentParser(
    prog = 'weiboPicDownloader'
)
group = parser.add_mutually_exclusive_group(required = True)
group.add_argument(
    '-u', metavar = 'user', dest = 'users', nargs = '+',
    help = 'specify nickname or id of weibo users'
)
group.add_argument(
    '-f', metavar = 'file', dest = 'files', nargs = '+',
    help = 'import list of users from files'
)
parser.add_argument(
    '-d', metavar = 'directory', dest = 'directory',
    help = 'set picture saving path'
)
parser.add_argument(
    '-s', metavar = 'size', dest = 'size',
    default = 20, type = int,
    help = 'set size of thread pool'
)
parser.add_argument(
    '-r', metavar = 'retry', dest = 'retry',
    default = 2, type = int,
    help = 'set maximum number of retries'
)
parser.add_argument(
    '-i', metavar = 'interval', dest = 'interval',
    default = 1, type = float,
    help = 'set interval for feed requests'
)
parser.add_argument(
    '-c', metavar = 'cookie', dest = 'cookie',
    help = 'set cookie if needed'
)
parser.add_argument(
    '-b', metavar = 'boundary', dest = 'boundary',
    default = ':',
    help = 'focus on weibos in the id range'
)
parser.add_argument(
    '-n', metavar = 'name', dest = 'name', default = '{name}',
    help = 'customize naming format'
)
parser.add_argument(
    '-v', dest = 'video', action = 'store_true',
    help = 'download videos together'
)
parser.add_argument(
    '-o', dest = 'overwrite', action = 'store_true',
    help = 'overwrite existing files'
)

def nargs_fit(parser, args):
    flags = parser._option_string_actions
    short_flags = [flag for flag in flags.keys() if len(flag) == 2]
    long_flags = [flag for flag in flags.keys() if len(flag) > 2]
    short_flags_with_nargs = set([flag[1] for flag in short_flags if flags[flag].nargs])
    short_flags_without_args = set([flag[1] for flag in short_flags if flags[flag].nargs == 0])
    validate = lambda part : (re.match(r'-[^-]', part) and (set(part[1:-1]).issubset(short_flags_without_args) and '-' + part[-1] in short_flags)) or (part.startswith('--') and part in long_flags)

    greedy = False
    for index, arg in enumerate(args):
        if arg.startswith('-'):
            valid = validate(arg)
            if valid and arg[-1] in short_flags_with_nargs:
                greedy = True
            elif valid:
                greedy = False
            elif greedy:
                args[index] = ' ' + args[index]
    return args

def print_fit(string, pin = False):
    if is_python2:
        string = string.encode(system_encoding)
    if pin == True:
        sys.stdout.write('\r\033[K')
        sys.stdout.write(string)
        sys.stdout.flush()
    else:
        sys.stdout.write(string + '\n')

def input_fit(string = ''):
    if is_python2:
        return raw_input(string.encode(system_encoding)).decode(system_encoding)
    else:
        return input(string)

def merge(*dicts):
    result = {}
    for dictionary in dicts: result.update(dictionary)
    return result

def quit(string = ''):
    print_fit(string)
    exit()

def make_dir(path):
    try:
        os.makedirs(path)
    except Exception as e:
        quit(str(e))

def confirm(message):
    while True:
        answer = input_fit('{} [Y/n] '.format(message)).strip()
        if answer == 'y' or answer == 'Y':
            return True
        elif answer == 'n' or answer == 'N':
            return False
        print_fit('unexpected answer')

def progress(part, whole, percent = False):
    if percent:
        return '{}/{}({}%)'.format(part, whole, int(float(part) / whole * 100))
    else:
        return '{}/{}'.format(part, whole)

def request_fit(method, url, max_retry = 0, cookie = None, stream = False):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 9; Pixel 3 XL) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.80 Mobile Safari/537.36',
        'referer': 'https://m.weibo.cn/',
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest'
    }
    if cookie:
        headers['Cookie'] = cookie
    try:
        return requests.request(method, url, headers = headers, timeout = 10, stream = stream, verify = False)
    except requests.exceptions.Timeout:
        print_fit('请求超时: {}'.format(url))
        raise
    except requests.exceptions.RequestException as e:
        print_fit('请求异常: {} - {}'.format(url, str(e)))
        raise

def read_from_file(path):
    try:
        with open(path, 'r') as f:
            return [line.strip().decode(system_encoding) if is_python2 else line.strip() for line in f]
    except Exception as e:
        quit(str(e))

def nickname_to_uid(nickname):
    url = 'https://m.weibo.cn/n/{}'.format(nickname)
    try:
        response = request_fit('GET', url, cookie = token)
        if 200 <= response.status_code < 400:
            # 1) 直接从最终URL提取 /u/<uid>
            m = re.search(r'/u/(\d+)(?:$|[/?#])', response.url)
            if m:
                return m.group(1)

            # 2) 若被带到 visitor 域，解析其 query 中的真实 m.weibo.cn 目标URL，再从中提取 UID
            if 'visitor.passport.weibo.cn/visitor/visitor' in response.url:
                try:
                    from urllib.parse import urlparse, parse_qs, unquote
                except Exception:
                    from urlparse import urlparse, parse_qs
                    from urllib import unquote
                parsed = urlparse(response.url)
                q = parse_qs(parsed.query)
                target = q.get('url', [None])[0]
                if target:
                    target = unquote(target)
                    m2 = re.search(r'/u/(\d+)(?:$|[/?#])', target)
                    if m2:
                        return m2.group(1)
                    # 若目标仍是昵称页，尝试再请求一次目标URL
                    try:
                        t_resp = request_fit('GET', target, cookie = token)
                        if 200 <= t_resp.status_code < 400:
                            m3 = re.search(r'/u/(\d+)(?:$|[/?#])', t_resp.url)
                            if m3:
                                return m3.group(1)
                    except Exception:
                        pass

            # 3) 使用 Web 接口：根据个性域名/昵称获取资料（更稳定）
            try:
                api_url = 'https://weibo.com/ajax/profile/info?custom={}'.format(quote(nickname))
                api_resp = request_fit('GET', api_url, cookie = token)
                if api_resp.status_code == 200:
                    info = json.loads(api_resp.text)
                    user_info = (info.get('data') or {}).get('user') or {}
                    uid = user_info.get('id') or user_info.get('idstr')
                    if uid:
                        return str(uid)
            except Exception:
                pass

            # 4) 若仍失败，使用 m 站搜索API兜底（可能误匹配）
            try:
                search_url = 'https://m.weibo.cn/api/container/getIndex?containerid=100103type=3&q={}'.format(quote(nickname))
                s_resp = request_fit('GET', search_url, cookie = token)
                if s_resp.status_code == 200:
                    data = json.loads(s_resp.text)
                    candidates = []
                    for card in (data.get('data', {}).get('cards') or []):
                        user_obj = card.get('user')
                        if isinstance(user_obj, dict):
                            candidates.append(user_obj)
                        for sub in (card.get('card_group') or []):
                            if isinstance(sub, dict):
                                if isinstance(sub.get('user'), dict):
                                    candidates.append(sub['user'])
                                if isinstance(sub.get('users'), list):
                                    candidates.extend([u for u in sub['users'] if isinstance(u, dict)])
                    for u in candidates:
                        if u.get('screen_name') == nickname and (u.get('idstr') or u.get('id')):
                            return u.get('idstr') or str(u.get('id'))
                    for u in candidates:
                        if nickname in (u.get('screen_name') or '') and (u.get('idstr') or u.get('id')):
                            return u.get('idstr') or str(u.get('id'))
                    if candidates:
                        u0 = candidates[0]
                        if u0.get('idstr') or u0.get('id'):
                            return u0.get('idstr') or str(u0.get('id'))
            except Exception:
                pass
        elif response.status_code == 404:
            print_fit('警告: 用户昵称 "{}" 不存在'.format(nickname))
        else:
            print_fit('警告: 获取用户ID时请求失败 (状态码{})'.format(response.status_code))
    except Exception as e:
        print_fit('警告: 获取用户ID时出错: {}'.format(str(e)))
    return None

def uid_to_nickname(uid):
    url = 'https://m.weibo.cn/api/container/getIndex?type=uid&value={}'.format(uid)
    try:
        response = request_fit('GET', url, cookie = token)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data.get('ok') == 1 and 'data' in data and 'userInfo' in data['data']:
                return data['data']['userInfo']['screen_name']
        elif response.status_code == 432:
            print_fit('警告: API请求被限制 (状态码432)，可能需要添加Cookie或稍后重试')
        else:
            print_fit('警告: API请求失败 (状态码{})'.format(response.status_code))
    except Exception as e:
        print_fit('警告: 获取用户信息时出错: {}'.format(str(e)))
    return None

def bid_to_mid(string):
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    alphabet = {x: n for n, x in enumerate(alphabet)}

    splited = [string[(g + 1) * -4 : g * -4 if g * -4 else None] for g in reversed(range(math.ceil(len(string) / 4.0)))]
    convert = lambda s : str(sum([alphabet[c] * (len(alphabet) ** k) for k, c in enumerate(reversed(s))])).zfill(7)
    return int(''.join(map(convert, splited)))

def parse_date(text):
    now = datetime.datetime.now()
    
    # 处理"X小时前"、"X分钟前"等格式
    if u'前' in text:
        if u'小时' in text:
            hours = int(re.search(r'\d+', text).group())
            return (now - datetime.timedelta(hours=hours)).date()
        elif u'分钟' in text:
            return now.date()
        else:
            return now.date()
    
    # 处理"昨天"格式
    elif u'昨天' in text:
        return now.date() - datetime.timedelta(days=1)
    
    # 处理"X月X日"格式
    elif re.search(r'^\d{1,2}月\d{1,2}日$', text):
        month, day = re.search(r'(\d{1,2})月(\d{1,2})日', text).groups()
        # 假设是今年的日期，如果月份大于当前月份，则认为是去年
        year = now.year
        if int(month) > now.month:
            year -= 1
        return datetime.datetime(year, int(month), int(day)).date()
    
    # 处理"X-X"格式（月-日）
    elif re.search(r'^\d{1,2}-\d{1,2}$', text):
        month, day = text.split('-')
        year = now.year
        if int(month) > now.month:
            year -= 1
        return datetime.datetime(year, int(month), int(day)).date()
    
    # 处理"YYYY-MM-DD"格式
    elif re.search(r'^\d{4}-\d{1,2}-\d{1,2}$', text):
        return datetime.datetime.strptime(text, '%Y-%m-%d').date()
    
    # 处理"MM-DD"格式
    elif re.search(r'^\d{1,2}-\d{1,2}$', text):
        month, day = text.split('-')
        year = now.year
        if int(month) > now.month:
            year -= 1
        return datetime.datetime(year, int(month), int(day)).date()
    
    # 处理英文日期格式，如 "Fri Mar 14 18:55:46 +0800 2025"
    elif re.search(r'^[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\+0800\s+\d{4}$', text):
        try:
            # 解析英文日期格式
            date_obj = datetime.datetime.strptime(text, '%a %b %d %H:%M:%S +0800 %Y')
            return date_obj.date()
        except ValueError:
            print_fit('无法解析英文日期格式: {}，使用当前日期'.format(text))
            return now.date()
    
    # 如果无法解析，返回当前日期
    else:
        print_fit('无法解析日期格式: {}，使用当前日期'.format(text))
        return now.date()

def compare(standard, operation, candidate):
    for target in candidate:
        try:
            result = '>=<'
            if standard > target: result = '>'
            elif standard == target: result = '='
            else: result = '<'
            return result in operation
        except TypeError:
            pass

def get_resources(uid, video, interval, limit, start_page=1):
    page = start_page
    size = 50  # 增加每页数量，提高下载效率
    amount = 0
    total = 0
    empty = 0
    aware = 3  # 增加重试次数，提高成功率
    exceed = False
    resources = []

    max_pages = 10000  # 设置最大页数限制，支持更多页数
    while empty < aware and not exceed and page <= max_pages:
        try:
            url = 'https://m.weibo.cn/api/container/getIndex?count={}&page={}&containerid=107603{}'.format(size, page, uid)
            print_fit('正在请求第{}页...'.format(page))
            response = request_fit('GET', url, cookie = token)
            
            if response.status_code == 432:
                print_fit('API请求被限制 (状态码432)，可能需要添加Cookie')
                empty = aware
                break
            elif response.status_code != 200:
                print_fit('API请求失败，状态码: {}'.format(response.status_code))
                empty += 1
                continue
                
            json_data = json.loads(response.text)
            
            if json_data.get('ok') != 1:
                error_msg = json_data.get('msg') or json_data.get('message') or json_data.get('errmsg') or ''
                if not error_msg:
                    # 打印一小段响应体帮助定位
                    snippet = response.text[:160].replace('\n', ' ')
                    error_msg = '未知错误，响应片段: {}'.format(snippet)
                print_fit('API返回错误: {}'.format(error_msg))
                # 若触发极验验证，切换到桌面 Web 接口
                if json_data.get('ok') == -100 and 'geetest' in response.text:
                    print_fit('检测到极验验证，切换到桌面接口抓取...')
                    return get_resources_web(uid, video, interval, limit, start_page=1)
                # 如果是"这里还没有内容"，说明已经到达最后一页
                if '还没有内容' in error_msg:
                    print_fit('已到达最后一页，停止扫描')
                    empty = aware
                    break
                empty += 1
                continue
                
        except requests.exceptions.Timeout:
            print_fit('请求超时，跳过第{}页'.format(page))
            empty += 1
            continue
        except json.JSONDecodeError as e:
            print_fit('JSON解析失败: {}'.format(str(e)))
            empty += 1
            continue
        except Exception as e:
            print_fit('请求异常: {}'.format(str(e)))
            empty += 1
            continue
        else:
            empty = empty + 1 if json_data['ok'] == 0 else 0
            if total == 0 and 'cardlistInfo' in json_data['data']: total = json_data['data']['cardlistInfo']['total']
            cards = json_data['data']['cards']
            for card in cards:
                if 'mblog' in card:
                    mblog = card['mblog']
                    if 'isTop' in mblog and mblog['isTop']: continue
                    mid = int(mblog['mid'])
                    date = parse_date(mblog['created_at'])
                    mark = {'mid': mid, 'bid': mblog['bid'], 'date': date, 'text': mblog['text']}
                    amount += 1
                    if compare(limit[0], '>', [mid, date]): exceed = True
                    if compare(limit[0], '>', [mid, date]) or compare(limit[1], '<', [mid, date]): continue
                    if 'pics' in mblog:
                        for index, pic in enumerate(mblog['pics'], 1):
                            if 'large' in pic:
                                resources.append(merge({'url': pic['large']['url'], 'index': index, 'type': 'photo'}, mark))
                    elif 'page_info' in mblog and video:
                        # 安全获取 page_info 与 media_info（可能为 None）
                        page_info = mblog.get('page_info') or {}
                        media_info = page_info.get('media_info') or {}

                        # 按质量优先级排序视频流
                        quality_streams = []

                        # 首先检查 page_info 中的 URLs（通常包含更高质量）
                        urls = page_info.get('urls')
                        if isinstance(urls, dict) and urls:
                            # 按质量优先级排序
                            if urls.get('mp4_4k_mp4'):
                                quality_streams.append(('4K', urls['mp4_4k_mp4']))
                            if urls.get('mp4_2k_mp4'):
                                quality_streams.append(('2K', urls['mp4_2k_mp4']))
                            if urls.get('mp4_1080p_mp4'):
                                quality_streams.append(('1080p', urls['mp4_1080p_mp4']))
                            if urls.get('mp4_720p_mp4'):
                                quality_streams.append(('720p', urls['mp4_720p_mp4']))
                            if urls.get('mp4_hd_mp4'):
                                quality_streams.append(('HD', urls['mp4_hd_mp4']))
                            if urls.get('mp4_ld_mp4'):
                                quality_streams.append(('LD', urls['mp4_ld_mp4']))

                            # 可选：尝试从URL中提取分辨率信息（不影响主流程）
                            try:
                                for key, u in urls.items():
                                    if u and isinstance(u, str) and 'template=' in u:
                                        _ = u.split('template=')[1].split('&')[0]
                            except Exception:
                                pass

                        # 如果没有URLs，则检查 media_info（可能为 None 或非字典）
                        if not quality_streams and isinstance(media_info, dict):
                            if media_info.get('mp4_4k_mp4'):
                                quality_streams.append(('4K', media_info['mp4_4k_mp4']))
                            if media_info.get('mp4_2k_mp4'):
                                quality_streams.append(('2K', media_info['mp4_2k_mp4']))
                            if media_info.get('mp4_1080p_mp4'):
                                quality_streams.append(('1080p', media_info['mp4_1080p_mp4']))
                            if media_info.get('mp4_720p_mp4'):
                                quality_streams.append(('720p', media_info['mp4_720p_mp4']))
                            if media_info.get('mp4_hd_url'):
                                quality_streams.append(('HD', media_info['mp4_hd_url']))
                            if media_info.get('stream_url_hd'):
                                quality_streams.append(('HD_Stream', media_info['stream_url_hd']))
                            if media_info.get('stream_url'):
                                quality_streams.append(('Stream', media_info['stream_url']))

                        # 选择最高质量的视频
                        if quality_streams:
                            best_quality, best_url = quality_streams[0]
                            resources.append(merge({'url': best_url, 'type': 'video', 'quality': best_quality}, mark))
            # 统计图片和视频数量
            photo_count = len([r for r in resources if r.get('type') == 'photo'])
            video_count = len([r for r in resources if r.get('type') == 'video'])
            print_fit('{} {}(#{}) - 图片:{} 视频:{}'.format('analysing weibos...' if empty < aware and not exceed else 'finish analysis', progress(amount, total), page, photo_count, video_count), pin = True)
            page += 1
        finally:
            time.sleep(interval)

    print_fit('\npractically scan {} weibos, get {} {}'.format(amount, len(resources), 'resources' if video else 'pictures'))
    return resources

def get_cookie_value(cookie_str, key):
    try:
        parts = [p.strip() for p in (cookie_str or '').split(';') if p.strip()]
        for p in parts:
            if p.startswith(key + '='):
                return p[len(key) + 1:]
    except Exception:
        pass
    return None

def request_fit_web(method, url, cookie = None, stream = False):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://weibo.com/',
        'Accept': 'application/json, text/plain, */*'
    }
    if cookie:
        headers['Cookie'] = cookie
        xsrf = get_cookie_value(cookie, 'XSRF-TOKEN')
        if xsrf:
            headers['X-XSRF-TOKEN'] = xsrf
    return requests.request(method, url, headers = headers, timeout = 10, stream = stream, verify = False)

def get_resources_web(uid, video, interval, limit, start_page = 1):
    page = start_page
    size = 50  # 增加每页数量，提高下载效率
    amount = 0
    total = 0
    resources = []
    empty_pages = 0
    aware = 3

    while empty_pages < aware:
        try:
            url = 'https://weibo.com/ajax/statuses/mymblog?uid={}&page={}&count={}&feature=0'.format(uid, page, size)
            print_fit('正在请求(桌面)第{}页...'.format(page))
            response = request_fit_web('GET', url, cookie = token)
            if response.status_code != 200:
                print_fit('桌面接口失败，状态码: {}'.format(response.status_code))
                empty_pages += 1
                time.sleep(interval)
                continue

            data = json.loads(response.text)
            if not isinstance(data, dict) or not data.get('data') or not data['data'].get('list'):
                empty_pages += 1
                time.sleep(interval)
                continue

            lst = data['data']['list']
            total = max(total, data['data'].get('count', 0))

            for mblog in lst:
                try:
                    if mblog.get('isTop'): 
                        continue
                    mid = int(mblog.get('mid') or mblog.get('id') or 0)
                    date = parse_date(mblog.get('created_at') or '')
                    mark = {'mid': mid, 'bid': mblog.get('bid'), 'date': date, 'text': mblog.get('text', '')}
                    amount += 1

                    if compare(limit[0], '>', [mid, date]):
                        return resources
                    if compare(limit[0], '>', [mid, date]) or compare(limit[1], '<', [mid, date]):
                        continue

                    # 图片
                    pic_ids = mblog.get('pic_ids') or []
                    pic_infos = mblog.get('pic_infos') or {}
                    index = 0
                    for pid in pic_ids:
                        index += 1
                        info = pic_infos.get(pid) or {}
                        large = (info.get('largest') or info.get('original') or info.get('large') or {}).get('url')
                        if not large:
                            # 兜底从多分辨率字段取
                            for key in ['mw2000','mw690','bmiddle','thumbnail']:
                                u = (info.get(key) or {}).get('url')
                                if u:
                                    large = u
                                    break
                        if large:
                            resources.append(merge({'url': large, 'index': index, 'type': 'photo'}, mark))

                    # 视频
                    if video:
                        page_info = mblog.get('page_info') or {}
                        media_info = page_info.get('media_info') or {}
                        best = None
                        for key in ['mp4_4k_mp4','mp4_2k_mp4','mp4_1080p_mp4','mp4_720p_mp4','mp4_hd_url','stream_url_hd','stream_url','mp4_sd_url']:
                            if media_info.get(key):
                                best = media_info.get(key)
                                break
                        if best:
                            resources.append(merge({'url': best, 'type': 'video', 'quality': 'web'}, mark))
                except Exception:
                    pass

            print_fit('{} {}(#{}) - 图片:{} 视频:{}'.format('analysing weibos...', progress(amount, total), page, len([r for r in resources if r.get('type') == 'photo']), len([r for r in resources if r.get('type') == 'video'])), pin = True)
            page += 1
            empty_pages = 0 if lst else empty_pages + 1
        except Exception as e:
            print_fit('桌面接口异常: {}'.format(str(e)))
            empty_pages += 1
        finally:
            time.sleep(interval * 0.5)  # 减少桌面版API的请求间隔，提高速度

    print_fit('\npractically scan {} weibos, get {} {}'.format(amount, len(resources), 'resources' if video else 'pictures'))
    return resources

def format_name(item):
    # 从URL中提取文件扩展名
    url = item['url']
    if '?' in url:
        url = url.split('?')[0]
    
    # 获取文件扩展名
    if '.' in url:
        ext = url.split('.')[-1].lower()
        # 确保扩展名是有效的图片/视频格式
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'mp4', 'mov', 'avi']:
            ext = 'png'  # 默认扩展名
    else:
        ext = 'mp4'  # 默认扩展名
    
    # 格式化日期为 YYYY-MM-DD 格式，处理日期为None的情况
    if item['date'] is not None:
        date_str = item['date'].strftime('%Y-%m-%d')
    else:
        # 如果日期为None，使用当前日期
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # 获取用户昵称（从全局变量中获取）
    nickname = getattr(args, 'current_nickname', 'unknown')
    
    # 如果有索引号，添加到文件名中
    index_str = ''
    if 'index' in item and item['index'] > 1:
        index_str = f'-{item["index"]:02d}'
    
    # 组合文件名：日期-昵称-微博ID[索引][质量].扩展名
    # 添加微博ID来避免文件名冲突
    mid_str = str(item.get('mid', 'unknown'))
    
    # 如果是视频，添加质量信息
    quality_str = ''
    if item.get('type') == 'video' and 'quality' in item:
        quality_str = f"-{item['quality']}"
    
    filename = f"{date_str}-{nickname}-{mid_str}{index_str}{quality_str}.{ext}"
    
    # 清理文件名中的非法字符
    def safeify(name):
        template = {u'\\': u'＼', u'/': u'／', u':': u'：', u'*': u'＊', u'?': u'？', u'"': u'＂', u'<': u'＜', u'>': u'＞', u'|': u'｜'}
        for illegal in template:
            name = name.replace(illegal, template[illegal])
        return name
    
    return safeify(filename)

def download(url, path, overwrite):
    if os.path.exists(path) and not overwrite: 
        print_fit('文件已存在，跳过: {}'.format(os.path.basename(path)))
        return True
    try:
        response = request_fit('GET', url, stream = True, cookie = token)
        if response.status_code != 200:
            print_fit('下载失败，状态码: {} - {}'.format(response.status_code, os.path.basename(path)))
            return False
        
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size = 512):
                if chunk:
                    f.write(chunk)
        
        # 验证文件大小
        if os.path.getsize(path) == 0:
            print_fit('下载的文件为空: {}'.format(os.path.basename(path)))
            os.remove(path)
            return False
            
        # print_fit('下载成功: {} ({:.1f}KB)'.format(os.path.basename(path), os.path.getsize(path)/1024))
        return True
    except Exception as e:
        print_fit('下载异常: {} - {}'.format(str(e), os.path.basename(path)))
        if os.path.exists(path): os.remove(path)
        return False

args = parser.parse_args(nargs_fit(parser, sys.argv[1:]))

if args.users:
    users = [user.decode(system_encoding) for user in args.users] if is_python2 else args.users
elif args.files:
    users = [read_from_file(path.strip()) for path in args.files]
    users = reduce(lambda x, y : x + y, users)
users = [user.strip() for user in users]

if args.directory:
    base = args.directory
    if os.path.exists(base):
        if not os.path.isdir(base): quit('saving path is not a directory')
    elif confirm('directory "{}" doesn\'t exist, help to create?'.format(base)):
        make_dir(base)
    else:
        quit('do it youself :)')
else:
    base = os.path.join(os.path.dirname(__file__), 'weiboPic')
    if not os.path.exists(base): make_dir(base)

boundary = args.boundary.split(':')
boundary = boundary * 2 if len(boundary) == 1 else boundary

def parse_boundary_point(p):
    if p == '':
        return None
    elif p.startswith('@'):
        # 处理 @YYYYMMDD 格式
        try:
            return datetime.datetime.strptime(p[1:], '%Y%m%d').date()
        except ValueError:
            quit('invalid date format: {}'.format(p))
    elif re.search(r'^\d{4}-\d{1,2}-\d{1,2}$', p):
        # 处理 YYYY-MM-DD 格式
        try:
            return datetime.datetime.strptime(p, '%Y-%m-%d').date()
        except ValueError:
            quit('invalid date format: {}'.format(p))
    elif re.search(r'^\d+$', p):
        # 处理纯数字（微博ID）
        return int(p)
    else:
        # 处理其他格式（如bid）
        try:
            return bid_to_mid(p)
        except:
            quit('invalid boundary format: {}'.format(p))

try:
    boundary[0] = parse_boundary_point(boundary[0])
    boundary[1] = parse_boundary_point(boundary[1])
    
    # 如果两个边界都是日期类型，检查顺序
    if (isinstance(boundary[0], datetime.date) and 
        isinstance(boundary[1], datetime.date) and 
        boundary[0] > boundary[1]):
        quit('start date must be before end date')
        
except Exception as e:
    quit('invalid id range {}: {}'.format(args.boundary, str(e)))

# 设置Cookie，如果用户提供了SUB值，则使用SUB格式，否则使用完整Cookie
if args.cookie:
    if args.cookie.startswith('SUB='):
        token = args.cookie
    else:
        token = 'SUB={}'.format(args.cookie)
else:
    # 尝试从环境变量读取，避免将敏感 SUB 写入代码
    env_cookie = os.environ.get('WEIBO_SUB') or os.environ.get('WEIBO_COOKIE')
    if env_cookie:
        token = env_cookie if env_cookie.startswith('SUB=') else 'SUB={}'.format(env_cookie)
    else:
        quit('missing cookie: 请通过 -c 传入 SUB，或设置环境变量 WEIBO_SUB')
pool = concurrent.futures.ThreadPoolExecutor(max_workers = args.size)
# print(users)
for number, user in enumerate(users, 1):
    
    print_fit('{}/{} {}'.format(number, len(users), time.ctime()))
    
    if re.search(r'^\d{10}$', user):
        nickname = uid_to_nickname(user)
        uid = user
    else:
        nickname = user
        uid = nickname_to_uid(user)

    if not nickname or not uid:
        print_fit('invalid account {}'.format(user))
        print_fit('-' * 30)
        continue
    print_fit('{} {}'.format(nickname, uid))
    
    # 设置当前用户昵称，供format_name函数使用
    args.current_nickname = nickname
    
    try:
        resources = get_resources(uid, args.video, args.interval, boundary)
    except KeyboardInterrupt:
        quit()

    album = os.path.join(base, nickname)
    if resources and not os.path.exists(album): make_dir(album)

    retry = 0
    while resources and retry <= args.retry:
        
        if retry > 0: print_fit('automatic retry {}'.format(retry))

        total = len(resources)
        tasks = []
        done = 0
        failed = {}
        cancel = False

        for resource in resources:
            path = os.path.join(album, format_name(resource))
            tasks.append(pool.submit(download, resource['url'], path, args.overwrite))

        while done != total:
            try:
                done = 0
                for index, task in enumerate(tasks):
                    if task.done() == True:
                        done += 1
                        if task.cancelled(): continue
                        elif task.result() == False: failed[index] = ''
                    elif cancel:
                        if not task.cancelled(): task.cancel()
                time.sleep(0.5)
            except KeyboardInterrupt:
                cancel = True
            finally:
                if not cancel:
                    print_fit('{} {}'.format(
                        'downloading...' if done != total else 'all tasks done',
                        progress(done, total, True)
                    ), pin = True)
                else:
                    print_fit('waiting for cancellation... ({})'.format(total - done), pin = True) 

        if cancel: quit()
        print_fit('\nsuccess {}, failure {}, total {}'.format(total - len(failed), len(failed), total))

        resources = [resources[index] for index in failed]
        retry += 1

    for resource in resources: print_fit('{} failed'.format(resource['url']))
    print_fit('-' * 30)

quit('bye bye')