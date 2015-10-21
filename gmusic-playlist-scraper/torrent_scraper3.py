# coding=utf-8

from __future__ import print_function

import argparse
import re
import unicodedata
import os
from lxml import etree

import requests

from gmusicapi import Mobileclient

# drops unicode strings like 'POLIÇA' to closest ASCII match for searching
def normalize(unistr, sub=''):
    if sub:
        return re.sub(r'[^a-zA-Z0-9]', sub, unicodedata.normalize('NFKD', unistr).encode('ascii', 'ignore'))
    else:
        return unicodedata.normalize('NFKD', unistr).encode('ascii', 'ignore')



def get_gmusic_playlist(login, password, search_playlist_title):
    api = Mobileclient()
    api.login(login, password)
    all_playlists = api.get_all_user_playlist_contents()
    playlist = next(entry for entry in all_playlists if entry[u'name'] == search_playlist_title)
    album_list = {(entry[u'track'][u'albumArtist'], entry[u'track'][u'album'])
                  for entry in playlist[u'tracks'] if 'track' in entry}
    api.logout()
    return album_list


def get_torrent_hashes(album_list, category):
    hash_list = []
    not_found_list = []

    for album_artist in list(album_list):
        text_string = ' - '.join(album_artist)
        search_string = normalize(' '.join(album_artist), '%20').replace(' ', '+')
        query = 'http://torrentproject.se/?s=' + search_string + '&out=json'
        print('searching for %s' % text_string)
        r = requests.get(query)

        hits = r.json()
        best_result = find_best_match(hits, category, album_artist)
        if best_result['hash'] is not None:
            hash_list.append({'artist': album_artist[0], 'album': album_artist[1], 'title': text_string, 'hash': best_result['hash']})
        else:
            not_found_list.append({'title': text_string,'search_string':search_string, 'message': best_result['message']})

    if len(not_found_list) > 1:
        print('\nThe following searches were unsuccessful:')
        for item in not_found_list:
            print(item['title'] + ' (search string=\"' + 
                item['search_string'] + '\"): ' + item['message'])
    
    return hash_list


def find_best_match(hits, category, artist_album):
    best_match = {'hash': None, 'message': ''}

    if hits['total_found'] == '0':
        best_match['message'] = 'no results returned from torrentproject'
        return best_match

    results = [v for (k, v) in hits.items() if k != 'total_found' and all(normalize(query, ' ').lower() in v['title'].lower() for query in artist_album)]
    if len(results) == 0:
        best_match['message'] = 'results found but they didn\'t match the artist and album exactly.'
        return best_match

    results = sorted(results, key=lambda x: x[u'seeds'], reverse=True)
    if results[0]['seeds'] == 0:
        best_match['message'] = 'results found but none with seeds'
        return best_match
    
    lossless = ['flac', 'ape', 'lossless']
    if category.lower() in lossless:
        category = 'lossless'
    final_result = next((result for result in results if result['category'] == category), None)
    if final_result is None:
        best_match['message'] = 'results with seeds found but not in the desired format'
        return best_match

    best_match['hash'] = final_result['torrent_hash']
    best_match['message'] = 'success'
    print('found %s. adding...' % final_result['title'])
    return best_match


def add_torrents(hash_list, login, password, ip, port, music_path=None):
    utorrent_url = 'http://%s:%s/gui/' % (ip, port)
    utorrent_token = '%stoken.html' % utorrent_url

    http_auth = requests.auth.HTTPBasicAuth(login, password)
    token_request = requests.get(utorrent_token, auth=http_auth)
    if 'GUID' in token_request.cookies:
        cookies = {'GUID': token_request.cookies['GUID']}
    else:
        cookies = {}

    root = etree.HTML(token_request.text)
    token = root.xpath('//div[@id="token"]/text()')[0]

    successes = []
    failures = []

    for torrent in hash_list:
        if music_path and os.path.exists(music_path+'/'+normalize(torrent['artist'])+'/'+normalize(torrent['album'])):
            print('%s already exists in local purchases: are you sure you want to retrieve another copy? (y/n)' % torrent['title'])
            answer = raw_input('> ')
            if answer not in ['y', 'yes', 'Yes', 'Y']:
                continue
        print ('adding %s to uTorrent...' % torrent['title'])
        magnet_link = 'magnet:?xt=urn:btih:%s' % torrent['hash']
        request_params = {'action': 'add-url', 'token': token, 's': magnet_link}
        r = requests.get(url=utorrent_url, auth=http_auth, params=request_params, cookies=cookies)
        if r.status_code == 200:
            successes.append(torrent)
        else:
            torrent['status'] = r.status_code
            failures.append(torrent)

    if len(successes) > 0:
        print ('the following torrents were successfully added:')
        for result in successes:
            print (result['title'])

    if len(failures) > 0:
        print ('the following torrents had problems:')
        for result in failures:
            print (result['title'], result['status'])


def artist_album_type(s):
    try:
        artist, album = s.split(' - ')
        if not album:
            raise argparse.ArgumentParser.ArgumentTypeError
        return [unicode(artist, 'utf-8'), unicode(album, 'utf-8')]
    except:
        argparse.ArgumentParser.error('artist and album search string must be in format \"Artist title - Album title\" surrounded by quotes')

def gen_arguments():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-a", "--artist_album", help='artist and album search string in format \"Artist title - Album title\"', type=artist_album_type)
    group.add_argument("-p", "--playlist", help="Google music playlist title")
    # parser.add_argument("-c", "--config", help="config file containing all the other options besides playlist")
    parser.add_argument("-ip", default='127.0.0.1', help="port for the uTorrent WebAPI (default=127.0.0.1)")
    parser.add_argument("-port", default='8080', help="port for the uTorrent WebAPI (default=8080)")
    parser.add_argument("-lp", "--google_lp", help="login password for Google Music (and used by uTorrent) (format login(space, no brackets)password", required=True, nargs=2)
    parser.add_argument("-ulp", "--utorrent_lp", help="login password for uTorrent (if different to Google Music password)",)
    parser.add_argument("-f", "--format", default='mp3', help="optional desired format - eg 'mp3' or 'flac' (default=mp3)")
    parser.add_argument("-l", "--local", default="$HOME/downloads", help="optional check to not add torrent if it already exists locally. default=\"$HOME/Downloads\"")
    return parser.parse_args()

if __name__ == '__main__':

    args = gen_arguments()

    torrent_hashes = []
    if args.playlist:
        glogin, gpassword = args.google_lp
        albums = get_gmusic_playlist(glogin, gpassword, args.playlist)
        torrent_hashes = get_torrent_hashes(albums, args.format)
    elif args.artist_album:
        search = []
        torrent_hashes = get_torrent_hashes([args.artist_album], args.format)

    if len(torrent_hashes) > 0:
        ulogin, upassword = args.utorrent_lp or args.google_lp
        add_torrents(torrent_hashes, ulogin, upassword, args.ip, args.port, args.local)
        print ('finished!')
    else:
        print ('results found but nothing matched')
