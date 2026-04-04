<?php

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';
require __DIR__ . '/db.php';

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$basePath = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? '/'), '/');
if ($basePath !== '' && $basePath !== '/') {
    $path = substr($path, strlen($basePath)) ?: '/';
}

try {
    if ($method === 'GET' && $path === '/health') {
        json_response(['status' => 'ok']);
    }

    if ($method === 'GET' && $path === '/lessons') {
        $lessons = [];
        foreach (load_lessons() as $lesson) {
            $lessons[] = [
                'lesson_id' => $lesson['lesson_id'],
                'topic_name' => $lesson['topic_name'],
                'stage' => $lesson['stage'],
                'title' => $lesson['title'],
                'summary' => $lesson['summary'],
                'explanation' => $lesson['explanation'],
                'code_sample' => $lesson['code_sample'],
                'challenge' => $lesson['challenge'],
                'xp_reward' => $lesson['xp_reward'],
                'quiz' => [
                    'prompt' => $lesson['quiz']['prompt'],
                    'options' => $lesson['quiz']['options'],
                ],
            ];
        }
        json_response(['lessons' => $lessons]);
    }

    if ($method === 'POST' && $path === '/signup') {
        $payload = read_json_body();
        $username = trim((string)($payload['username'] ?? ''));
        $password = (string)($payload['password'] ?? '');
        if (strlen($username) < 3 || strlen($password) < 4) {
            json_response(['error' => 'Username must be at least 3 characters and password at least 4 characters.'], 400);
        }

        $check = db()->prepare('SELECT id FROM users WHERE username = :username');
        $check->execute(['username' => $username]);
        if ($check->fetch()) {
            json_response(['error' => 'Username already exists.'], 400);
        }

        $insert = db()->prepare(
            'INSERT INTO users (username, password_hash, xp, created_at) VALUES (:username, :password_hash, 0, NOW())'
        );
        $insert->execute([
            'username' => $username,
            'password_hash' => password_hash($password, PASSWORD_DEFAULT),
        ]);

        $userId = (int)db()->lastInsertId();
        $token = bin2hex(random_bytes(24));
        $session = db()->prepare('INSERT INTO sessions (token, user_id, created_at) VALUES (:token, :user_id, NOW())');
        $session->execute(['token' => $token, 'user_id' => $userId]);

        json_response([
            'token' => $token,
            'user_id' => $userId,
            'username' => $username,
            'xp' => 0,
        ], 201);
    }

    if ($method === 'POST' && $path === '/login') {
        $payload = read_json_body();
        $username = trim((string)($payload['username'] ?? ''));
        $password = (string)($payload['password'] ?? '');

        $stmt = db()->prepare('SELECT id, username, password_hash, xp FROM users WHERE username = :username');
        $stmt->execute(['username' => $username]);
        $user = $stmt->fetch();
        if (!$user || !password_verify($password, $user['password_hash'])) {
            json_response(['error' => 'Invalid username or password.'], 400);
        }

        $token = bin2hex(random_bytes(24));
        $session = db()->prepare('INSERT INTO sessions (token, user_id, created_at) VALUES (:token, :user_id, NOW())');
        $session->execute(['token' => $token, 'user_id' => $user['id']]);

        json_response([
            'token' => $token,
            'user_id' => (int)$user['id'],
            'username' => $user['username'],
            'xp' => (int)$user['xp'],
        ]);
    }

    if ($method === 'GET' && $path === '/profile') {
        $user = current_user();
        if (!$user) {
            json_response(['error' => 'Unauthorized.'], 401);
        }

        $stmt = db()->prepare(
            'SELECT lesson_id FROM lesson_progress WHERE user_id = :user_id ORDER BY completed_at DESC'
        );
        $stmt->execute(['user_id' => $user['id']]);
        $completed = $stmt->fetchAll();

        json_response([
            'user_id' => (int)$user['id'],
            'username' => $user['username'],
            'xp' => (int)$user['xp'],
            'completed_lessons' => count($completed),
            'completed_lesson_ids' => array_map(
                static fn(array $row): string => $row['lesson_id'],
                $completed
            ),
        ]);
    }

    if ($method === 'POST' && $path === '/submit-lesson') {
        $user = current_user();
        if (!$user) {
            json_response(['error' => 'Unauthorized.'], 401);
        }

        $payload = read_json_body();
        $lessonId = (string)($payload['lesson_id'] ?? '');
        $selectedIndex = (int)($payload['selected_index'] ?? -1);
        $lesson = lesson_map()[$lessonId] ?? null;
        if (!$lesson) {
            json_response(['error' => 'Unknown lesson.'], 400);
        }

        $correctIndex = (int)$lesson['quiz']['answer_index'];
        $isCorrect = $selectedIndex === $correctIndex;
        $partialXp = max(3, intdiv((int)$lesson['xp_reward'], 4));
        $xpGain = $isCorrect ? (int)$lesson['xp_reward'] : $partialXp;

        $existingStmt = db()->prepare(
            'SELECT score FROM lesson_progress WHERE user_id = :user_id AND lesson_id = :lesson_id'
        );
        $existingStmt->execute(['user_id' => $user['id'], 'lesson_id' => $lessonId]);
        $existing = $existingStmt->fetch();

        if (!$existing) {
            $insert = db()->prepare(
                'INSERT INTO lesson_progress (user_id, lesson_id, score, completed_at)
                 VALUES (:user_id, :lesson_id, :score, NOW())'
            );
            $insert->execute([
                'user_id' => $user['id'],
                'lesson_id' => $lessonId,
                'score' => $isCorrect ? 1 : 0,
            ]);

            $xpStmt = db()->prepare('UPDATE users SET xp = xp + :xp WHERE id = :user_id');
            $xpStmt->execute(['xp' => $xpGain, 'user_id' => $user['id']]);
        } elseif ((int)$existing['score'] === 0 && $isCorrect) {
            $bonus = (int)$lesson['xp_reward'] - $partialXp;
            $update = db()->prepare(
                'UPDATE lesson_progress SET score = 1, completed_at = NOW()
                 WHERE user_id = :user_id AND lesson_id = :lesson_id'
            );
            $update->execute(['user_id' => $user['id'], 'lesson_id' => $lessonId]);

            $xpStmt = db()->prepare('UPDATE users SET xp = xp + :xp WHERE id = :user_id');
            $xpStmt->execute(['xp' => $bonus, 'user_id' => $user['id']]);
            $xpGain = $bonus;
        } else {
            $xpGain = 0;
        }

        $xpRead = db()->prepare('SELECT xp FROM users WHERE id = :user_id');
        $xpRead->execute(['user_id' => $user['id']]);
        $newXp = (int)$xpRead->fetchColumn();

        json_response([
            'correct' => $isCorrect,
            'xp_gained' => $xpGain,
            'correct_answer_index' => $correctIndex,
            'explanation' => $lesson['quiz']['explanation'],
            'new_xp' => $newXp,
        ]);
    }

    if ($method === 'GET' && $path === '/leaderboard') {
        $stmt = db()->query(
            'SELECT users.username, users.xp, COUNT(lesson_progress.lesson_id) AS completed_lessons
             FROM users
             LEFT JOIN lesson_progress ON lesson_progress.user_id = users.id
             GROUP BY users.id, users.username, users.xp
             ORDER BY users.xp DESC, completed_lessons DESC, users.username ASC
             LIMIT 25'
        );
        $leaders = [];
        foreach ($stmt->fetchAll() as $index => $row) {
            $leaders[] = [
                'rank' => $index + 1,
                'username' => $row['username'],
                'xp' => (int)$row['xp'],
                'completed_lessons' => (int)$row['completed_lessons'],
            ];
        }

        json_response(['leaders' => $leaders]);
    }

    json_response(['error' => 'Not found.'], 404);
} catch (Throwable $exception) {
    json_response(['error' => 'Server error.'], 500);
}
