<?php
/**
 * Soft-compatible drop-in for soft.awwthat.com
 *
 * Upload this folder as the Soft site document root (or merge routes) when
 * Laravel /authenticate is crashing with HTTP 500.
 *
 * Edit users.json next to this file (or ../users.json).
 *
 * Endpoints:
 *   GET /authenticate?username=&key=&value=&is_alive=
 *   GET /logger?uva=
 *   GET /linetext
 *   GET /latest_version
 *   GET /update
 */

declare(strict_types=1);

header('Access-Control-Allow-Origin: *');

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$path = rtrim($path, '/') ?: '/';

$passphrase = 'raw_value';
$usersFile = is_file(__DIR__ . '/users.json') ? __DIR__ . '/users.json' : (__DIR__ . '/../users.json');
$liveFile = sys_get_temp_dir() . '/laneora_soft_live.json';

function load_users(string $file): array {
    if (!is_file($file)) {
        return [];
    }
    $data = json_decode((string) file_get_contents($file), true);
    return is_array($data['users'] ?? null) ? $data['users'] : [];
}

function load_live(string $file): array {
    if (!is_file($file)) {
        return [];
    }
    $data = json_decode((string) file_get_contents($file), true);
    return is_array($data) ? $data : [];
}

function save_live(string $file, array $live): void {
    file_put_contents($file, json_encode($live));
}

/** CryptoJS-compatible OpenSSL Salted__ AES-256-CBC */
function soft_encrypt(string $passphrase, string $plaintext): string {
    $salt = random_bytes(8);
    $keyIv = '';
    $block = '';
    while (strlen($keyIv) < 48) {
        $block = md5($block . $passphrase . $salt, true);
        $keyIv .= $block;
    }
    $key = substr($keyIv, 0, 32);
    $iv = substr($keyIv, 32, 16);
    $cipher = openssl_encrypt($plaintext, 'AES-256-CBC', $key, OPENSSL_RAW_DATA, $iv);
    return base64_encode('Salted__' . $salt . $cipher);
}

function find_user(array $users, string $username, string $password): ?array {
    $username = strtolower(trim($username));
    $password = strtolower(trim($password));
    foreach ($users as $user) {
        if (strtolower((string) ($user['username'] ?? '')) !== $username) {
            continue;
        }
        if (strtolower((string) ($user['password'] ?? '')) !== $password) {
            continue;
        }
        if (($user['active'] ?? true) === false) {
            return null;
        }
        return $user;
    }
    return null;
}

function default_streams(): array {
    return [
        'one' => ['url' => 'https://one.dat.com', 'store' => [], 'lst' => '{}', 'sst' => ''],
        'power' => ['url' => 'https://power.dat.com', 'store' => [], 'lst' => '{}', 'sst' => ''],
    ];
}

function build_payload(array $user, string $passphrase): array {
    $streams = $user['streams'] ?? default_streams();
    $active = $user['active_subs'] ?? array_keys($streams);
    if (is_string($active)) {
        $active = array_values(array_filter(explode(',', $active)));
    }
    $payload = [
        'status' => 'okie',
        'p' => (string) ($user['p'] ?? '0'),
        'px' => (string) ($user['px'] ?? 'none'),
        'pu' => (string) ($user['pu'] ?? ''),
        'pd' => (string) ($user['pd'] ?? ''),
        'active_subs' => implode(',', $active),
    ];
    foreach ($active as $name) {
        $stream = $streams[$name] ?? default_streams()[$name] ?? [
            'url' => 'https://one.dat.com',
            'store' => [],
            'lst' => '{}',
            'sst' => '',
        ];
        $payload[$name] = soft_encrypt($passphrase, json_encode($stream));
    }
    return $payload;
}

$users = load_users($usersFile);

if ($path === '/latest_version') {
    header('Content-Type: text/plain; charset=utf-8');
    echo '3.0.0';
    exit;
}

if ($path === '/linetext') {
    header('Content-Type: text/plain; charset=utf-8');
    echo 'Laneora Soft drop-in — Soft /authenticate replacement';
    exit;
}

if ($path === '/update') {
    http_response_code(200);
    exit;
}

if ($path === '/authenticate') {
    $username = (string) ($_GET['username'] ?? '');
    $key = (string) ($_GET['key'] ?? '');
    $value = (string) ($_GET['value'] ?? '');
    $isAlive = (string) ($_GET['is_alive'] ?? '');
    $user = find_user($users, $username, $key);
    if ($user === null) {
        header('Content-Type: text/plain; charset=utf-8');
        echo '0';
        exit;
    }
    $uva = strtolower(trim($username)) . ':' . $value . ':' . $isAlive;
    $live = load_live($liveFile);
    $live[$uva] = $value;
    save_live($liveFile, $live);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(build_payload($user, $passphrase));
    exit;
}

if ($path === '/logger') {
    $uva = (string) ($_GET['uva'] ?? '');
    $live = load_live($liveFile);
    if (!isset($live[$uva])) {
        $parts = explode(':', $uva);
        $live[$uva] = $parts[1] ?? '';
        save_live($liveFile, $live);
    }
    header('Content-Type: text/plain; charset=utf-8');
    echo (string) $live[$uva];
    exit;
}

if ($path === '/' || $path === '/health') {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['ok' => true, 'users' => count($users), 'dropin' => true]);
    exit;
}

http_response_code(404);
header('Content-Type: text/plain; charset=utf-8');
echo 'not found';
