<?php
/**
 * Plugin Name: Weekly Digest Unlisted
 * Description: 주간 다이제스트 전용 카테고리를 비공개 링크화 — 검색 색인·사이트맵·홈/피드/검색 목록에서 제외.
 *              직접 URL을 아는 사람만 접근 가능. (로그인/비밀번호 없음)
 *
 * 설치: 이 파일을 wp-content/mu-plugins/ 에 업로드하면 자동 활성화(별도 활성화 불필요).
 *       mu-plugins 폴더가 없으면 새로 만든다.
 *
 * 중요: 아래 WD_CATEGORY_SLUG 값을 앱(.env)의 WP_CATEGORY_SLUG 와 똑같이 맞출 것.
 */

if (!defined('ABSPATH')) { exit; }

const WD_CATEGORY_SLUG = 'wd-brief-k7m3q9x2';  // ← .env 의 WP_CATEGORY_SLUG 와 동일하게

/** 슬러그 → 카테고리 term_id (캐시) */
function wd_term_id() {
    static $id = null;
    if ($id === null) {
        $t = get_category_by_slug(WD_CATEGORY_SLUG);
        $id = $t ? (int) $t->term_id : 0;
    }
    return $id;
}

/** 지금 보고 있는 화면이 해당 카테고리(글 또는 아카이브)인가 */
function wd_is_target() {
    $id = wd_term_id();
    if (!$id) { return false; }
    if (is_category($id)) { return true; }
    if (is_singular('post') && in_category($id, get_queried_object_id())) { return true; }
    return false;
}

/** 1) 해당 화면에 noindex,nofollow,noarchive 강제 (WP 5.7+ wp_robots) */
add_filter('wp_robots', function ($robots) {
    if (wd_is_target()) {
        $robots['noindex']   = true;
        $robots['nofollow']  = true;
        $robots['noarchive'] = true;
        unset($robots['index'], $robots['follow']);
    }
    return $robots;
});

/** 2) 코어 사이트맵에서 제외 — 글(posts) */
add_filter('wp_sitemaps_posts_query_args', function ($args, $post_type) {
    if ($post_type === 'post' && wd_term_id()) {
        $args['category__not_in'] = array_merge(
            (array) ($args['category__not_in'] ?? []),
            [wd_term_id()]
        );
    }
    return $args;
}, 10, 2);

/** 2-b) 코어 사이트맵에서 제외 — 카테고리 term 자체 */
add_filter('wp_sitemaps_taxonomies_query_args', function ($args, $taxonomy) {
    if ($taxonomy === 'category' && wd_term_id()) {
        $args['exclude'] = array_merge((array) ($args['exclude'] ?? []), [wd_term_id()]);
    }
    return $args;
}, 10, 2);

/** 3) 홈/피드/검색 등 일반 목록에서 제외 (단, 그 카테고리 아카이브 자체는 정상 노출) */
add_action('pre_get_posts', function ($q) {
    if (is_admin() || !$q->is_main_query()) { return; }
    $id = wd_term_id();
    if (!$id) { return; }
    if ($q->is_home() || $q->is_feed() || $q->is_search()) {
        $not = (array) $q->get('category__not_in');
        $not[] = $id;
        $q->set('category__not_in', $not);
    }
});

/** 4) (보강) 메인 RSS 피드에서 해당 카테고리 글 제외 */
add_filter('the_posts', function ($posts, $q) {
    if (!is_admin() && $q->is_feed() && wd_term_id()) {
        $id = wd_term_id();
        $posts = array_filter($posts, function ($p) use ($id) {
            return !in_category($id, $p);
        });
        $posts = array_values($posts);
    }
    return $posts;
}, 10, 2);
