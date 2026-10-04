<?php
/**
 * Plugin Name: NeonaFM Commerce Upload Bridge
 * Description: Private admin-only bridge for inspecting Neona Commerce file storage and automating digital product uploads.
 * Version: 0.1.0
 * Author: NeonaFM
 */

if (!defined('ABSPATH')) { exit; }

add_action('rest_api_init', function () {
    register_rest_route('neonafm-commerce-bridge/v1', '/inspect', [
        'methods' => 'GET',
        'callback' => 'neonafm_cub_inspect',
        'permission_callback' => function () { return current_user_can('manage_options'); },
    ]);
});

function neonafm_cub_inspect() {
    $root = WP_PLUGIN_DIR . '/neona-commerce';
    $out = [
        'plugin_root' => $root,
        'exists' => is_dir($root),
        'classes' => [],
        'functions' => [],
        'matches' => [],
    ];

    foreach (get_declared_classes() as $class) {
        try {
            $r = new ReflectionClass($class);
            $file = $r->getFileName();
            if ($file && strpos(wp_normalize_path($file), wp_normalize_path($root) . '/') === 0) {
                $methods = [];
                foreach ($r->getMethods(ReflectionMethod::IS_PUBLIC) as $m) {
                    if ($m->getDeclaringClass()->getName() === $class) {
                        $methods[] = $m->getName();
                    }
                }
                $out['classes'][] = [
                    'name' => $class,
                    'file' => str_replace(wp_normalize_path($root) . '/', '', wp_normalize_path($file)),
                    'methods' => array_values($methods),
                ];
            }
        } catch (Throwable $e) {}
    }

    $defined = get_defined_functions();
    foreach (($defined['user'] ?? []) as $fn) {
        try {
            $r = new ReflectionFunction($fn);
            $file = $r->getFileName();
            if ($file && strpos(wp_normalize_path($file), wp_normalize_path($root) . '/') === 0) {
                $out['functions'][] = [
                    'name' => $fn,
                    'file' => str_replace(wp_normalize_path($root) . '/', '', wp_normalize_path($file)),
                ];
            }
        } catch (Throwable $e) {}
    }

    if (is_dir($root)) {
        $needles = ['_nc_versions', '_nc_current_version_id', 'storage_path', '.ncv', 'move_uploaded_file', 'wp_handle_upload', 'file_put_contents', 'download'];
        $it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS));
        foreach ($it as $file) {
            if (!$file->isFile() || strtolower($file->getExtension()) !== 'php') continue;
            if ($file->getSize() > 1024 * 1024) continue;
            $text = @file_get_contents($file->getPathname());
            if ($text === false) continue;
            $lines = preg_split('/\R/', $text);
            foreach ($lines as $i => $line) {
                foreach ($needles as $needle) {
                    if (stripos($line, $needle) !== false) {
                        $from = max(0, $i - 3);
                        $to = min(count($lines) - 1, $i + 6);
                        $snippet = [];
                        for ($j = $from; $j <= $to; $j++) {
                            $snippet[] = ($j + 1) . ': ' . $lines[$j];
                        }
                        $out['matches'][] = [
                            'file' => str_replace(wp_normalize_path($root) . '/', '', wp_normalize_path($file->getPathname())),
                            'needle' => $needle,
                            'line' => $i + 1,
                            'snippet' => implode("\n", $snippet),
                        ];
                        if (count($out['matches']) >= 120) break 3;
                        break;
                    }
                }
            }
        }
    }

    return rest_ensure_response($out);
}
