<?php

declare(strict_types=1);

function db(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $configPath = __DIR__ . '/config.php';
    if (!is_file($configPath)) {
        json_response(['error' => 'Missing API config.php file.'], 500);
    }

    $config = require $configPath;
    $dsn = sprintf(
        'mysql:host=%s;dbname=%s;charset=utf8mb4',
        $config['db_host'],
        $config['db_name']
    );

    try {
        $pdo = new PDO(
            $dsn,
            $config['db_user'],
            $config['db_pass'],
            [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            ]
        );
    } catch (PDOException $exception) {
        json_response(['error' => 'Database connection failed.'], 500);
    }

    return $pdo;
}

function current_user(): ?array
{
    $token = bearer_token();
    if ($token === '') {
        return null;
    }

    $stmt = db()->prepare(
        'SELECT users.id, users.username, users.xp
         FROM users
         INNER JOIN sessions ON sessions.user_id = users.id
         WHERE sessions.token = :token'
    );
    $stmt->execute(['token' => $token]);
    $user = $stmt->fetch();

    return $user ?: null;
}
