#!/usr/bin/env node
/**
 * ncm_api.js — 网易云音乐 API 封装（基于 NeteaseCloudMusicApi）
 * 用法:
 *   node ncm_api.js login_sms <phone> <code>     # 验证码登录
 *   node ncm_api.js login_pwd <phone> <password>  # 密码登录
 *   node ncm_api.js send_sms <phone>              # 发送验证码
 *   node ncm_api.js liked                         # 获取我喜欢的歌单
 *   node ncm_api.js url <song_id>                 # 获取歌曲URL
 *   node ncm_api.js search <keyword>              # 搜索
 *   node ncm_api.js check                         # 检查登录状态
 */
const path = require('path');
const fs = require('fs');
const NeteaseApi = require(path.join(process.env.HOME, 'node_modules/NeteaseCloudMusicApi'));

const COOKIE_FILE = '/home/jacob/robot/ncm_cookies.txt';
const LIKED_CACHE = '/home/jacob/robot/ncm_liked.json';

function saveCookies(response) {
    const rawCookies = response.cookie;
    if (rawCookies) {
        fs.writeFileSync(COOKIE_FILE, rawCookies);
        console.log('[NCM] Cookie 已保存');
    }
}

function loadCookies() {
    try {
        return fs.readFileSync(COOKIE_FILE, 'utf-8').trim();
    } catch { return ''; }
}

async function loginSms(phone, code) {
    try {
        const res = await NeteaseApi.login_cellphone({
            phone,
            captcha: code,
            countrycode: '86',
            cookie: loadCookies(),
        });
        if (res.body.code === 200) {
            saveCookies(res);
            const profile = res.body.profile || {};
            console.log(JSON.stringify({
                success: true,
                nickname: profile.nickname,
                uid: profile.userId,
                vip: (profile.vipType || 0) > 0
            }));
        } else {
            console.log(JSON.stringify({ success: false, msg: res.body.message || res.body.msg }));
        }
    } catch (e) {
        console.log(JSON.stringify({ success: false, msg: e.message }));
    }
}

async function loginPwd(phone, password) {
    try {
        const res = await NeteaseApi.login_cellphone({
            phone,
            password,
            countrycode: '86',
            cookie: loadCookies(),
        });
        if (res.body.code === 200) {
            saveCookies(res);
            const profile = res.body.profile || {};
            console.log(JSON.stringify({
                success: true,
                nickname: profile.nickname,
                uid: profile.userId,
                vip: (profile.vipType || 0) > 0
            }));
        } else {
            console.log(JSON.stringify({ success: false, msg: res.body.message || res.body.msg }));
        }
    } catch (e) {
        console.log(JSON.stringify({ success: false, msg: e.message }));
    }
}

async function sendSms(phone) {
    try {
        const res = await NeteaseApi.captcha_sent({
            phone,
            ctcode: '86',
        });
        console.log(JSON.stringify({ success: res.body.code === 200, msg: res.body.message }));
    } catch (e) {
        console.log(JSON.stringify({ success: false, msg: e.message }));
    }
}

async function checkLogin() {
    try {
        const res = await NeteaseApi.user_account({
            cookie: loadCookies(),
        });
        if (res.body.code === 200 && res.body.profile) {
            console.log(JSON.stringify({
                logged: true,
                nickname: res.body.profile.nickname,
                uid: res.body.profile.userId,
                vip: (res.body.profile.vipType || 0) > 0,
            }));
        } else {
            console.log(JSON.stringify({ logged: false }));
        }
    } catch (e) {
        console.log(JSON.stringify({ logged: false, msg: e.message }));
    }
}

async function getLiked() {
    try {
        // 先获取账号信息
        const acc = await NeteaseApi.user_account({ cookie: loadCookies() });
        if (acc.body.code !== 200 || !acc.body.profile) {
            console.log(JSON.stringify({ success: false, msg: '未登录' }));
            return;
        }
        const uid = acc.body.profile.userId;
        // 获取歌单
        const pl = await NeteaseApi.user_playlist({ uid, limit: 100, cookie: loadCookies() });
        const playlists = pl.body.playlist || [];
        let liked = playlists.find(p => p.specialType === 5 || (p.name && p.name.includes('我喜欢')));
        if (!liked && playlists.length) liked = playlists[0];
        if (!liked) {
            console.log(JSON.stringify({ success: false, msg: '没找到歌单' }));
            return;
        }
        // 获取详情
        const detail = await NeteaseApi.playlist_detail({ id: liked.id, cookie: loadCookies() });
        const tracks = (detail.body.playlist && detail.body.playlist.tracks) || [];
        const songs = tracks.map(t => ({
            id: t.id,
            name: t.name,
            artist: (t.ar || []).map(a => a.name).join(' / '),
            album: (t.al || {}).name || '',
            duration: Math.floor((t.dt || 0) / 1000),
        }));
        // 缓存
        const cache = { playlist_name: liked.name, songs, time: Date.now() };
        fs.writeFileSync(LIKED_CACHE, JSON.stringify(cache, null, 2));
        console.log(JSON.stringify({ success: true, name: liked.name, count: songs.length, songs: songs.slice(0, 50) }));
    } catch (e) {
        console.log(JSON.stringify({ success: false, msg: e.message }));
    }
}

async function getPlaylist(keyword) {
    try {
        const acc = await NeteaseApi.user_account({ cookie: loadCookies() });
        if (acc.body.code !== 200 || !acc.body.profile) {
            console.log(JSON.stringify({ success: false, msg: '未登录' }));
            return;
        }
        const uid = acc.body.profile.userId;
        const pl = await NeteaseApi.user_playlist({ uid, limit: 100, cookie: loadCookies() });
        const playlists = pl.body.playlist || [];
        // 模糊匹配歌单名
        const kw = keyword.toLowerCase();
        let matched = playlists.find(p => p.name && p.name.toLowerCase().includes(kw));
        if (!matched) {
            console.log(JSON.stringify({ success: false, msg: `没找到"${keyword}"歌单`, playlists: playlists.map(p => p.name) }));
            return;
        }
        const detail = await NeteaseApi.playlist_detail({ id: matched.id, cookie: loadCookies() });
        const tracks = (detail.body.playlist && detail.body.playlist.tracks) || [];
        const songs = tracks.map(t => ({
            id: t.id,
            name: t.name,
            artist: (t.ar || []).map(a => a.name).join(' / '),
            album: (t.al || {}).name || '',
            duration: Math.floor((t.dt || 0) / 1000),
        }));
        // 缓存
        const cache = { playlist_name: matched.name, songs, time: Date.now() };
        fs.writeFileSync(LIKED_CACHE, JSON.stringify(cache, null, 2));
        console.log(JSON.stringify({ success: true, name: matched.name, count: songs.length, songs: songs.slice(0, 50) }));
    } catch (e) {
        console.log(JSON.stringify({ success: false, msg: e.message }));
    }
}

async function getSongUrl(songId) {
    try {
        const res = await NeteaseApi.song_url({
            id: songId,
            br: 192000,
            cookie: loadCookies(),
        });
        const data = res.body.data || [];
        if (data[0] && data[0].url) {
            console.log(JSON.stringify({ success: true, url: data[0].url, br: data[0].br }));
        } else {
            console.log(JSON.stringify({ success: false, msg: '无法获取链接', fee: data[0]?.fee }));
        }
    } catch (e) {
        console.log(JSON.stringify({ success: false, msg: e.message }));
    }
}

async function search(keyword) {
    try {
        const res = await NeteaseApi.search({
            keywords: keyword,
            type: 1,
            limit: 10,
            cookie: loadCookies(),
        });
        const songs = (res.body.result && res.body.result.songs) || [];
        const results = songs.map(s => ({
            id: s.id,
            name: s.name,
            artist: (s.artists || []).map(a => a.name).join(' / '),
            album: (s.album || {}).name || '',
            duration: Math.floor((s.duration || 0) / 1000),
        }));
        console.log(JSON.stringify({ success: true, songs: results }));
    } catch (e) {
        console.log(JSON.stringify({ success: false, msg: e.message }));
    }
}

async function main() {
    const args = process.argv.slice(2);
    const cmd = args[0];
    switch (cmd) {
        case 'login_sms': await loginSms(args[1], args[2]); break;
        case 'login_pwd': await loginPwd(args[1], args[2]); break;
        case 'send_sms': await sendSms(args[1]); break;
        case 'check': await checkLogin(); break;
        case 'liked': await getLiked(); break;
        case 'playlist': await getPlaylist(args.slice(1).join(' ')); break;
        case 'url': await getSongUrl(args[1]); break;
        case 'search': await search(args.slice(1).join(' ')); break;
        default:
            console.log('用法: node ncm_api.js <command> [args...]');
            console.log('  login_sms <phone> <code>');
            console.log('  login_pwd <phone> <password>');
            console.log('  send_sms <phone>');
            console.log('  check');
            console.log('  liked');
            console.log('  url <song_id>');
            console.log('  search <keyword>');
    }
    // 确保进程退出
    setTimeout(() => process.exit(0), 1000);
}

main();
