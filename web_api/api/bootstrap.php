<?php

declare(strict_types=1);

function json_response(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

function read_json_body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || $raw === '') {
        return [];
    }

    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : [];
}

function bearer_token(): string
{
    $header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (strncmp($header, 'Bearer ', 7) === 0) {
        return trim(substr($header, 7));
    }

    return '';
}

function load_lessons(): array
{
    static $lessons = null;
    if ($lessons !== null) {
        return $lessons;
    }

    $path = __DIR__ . '/../data/lessons.json';
    $contents = file_get_contents($path);
    $decoded = json_decode($contents ?: '[]', true);
    $lessons = is_array($decoded) ? $decoded : [];
    return $lessons;
}

function lesson_map(): array
{
    static $map = null;
    if ($map !== null) {
        return $map;
    }

    $map = [];
    foreach (load_lessons() as $lesson) {
        $map[$lesson['lesson_id']] = $lesson;
    }

    return $map;
}
