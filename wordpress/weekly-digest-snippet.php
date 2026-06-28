<?php
/*
 * Weekly Digest — 비공개 링크화 + 독립(브런치) 렌더링.
 * Code Snippets 등록용 (scope: global, active). 실제 등록 시 맨 위 <?php ... 이 블록주석 다음 본문만 전송.
 * 동작:
 *  (1) 전용 카테고리 글/목록을 검색 색인·사이트맵·피드·홈/검색에서 제외 (비공개 링크)
 *  (2) 전용 카테고리 글/목록 요청을 template_redirect로 가로채 워드프레스 테마를 통째로 우회,
 *      자체 헤더 + 브런치풍 목록(썸네일 카드)/단일글로 직접 렌더 (도메인만 차용)
 */

if (!defined('WD_CATEGORY_SLUG')) {
    define('WD_CATEGORY_SLUG', 'wd-brief-k7m3q9x2');  // .env WP_CATEGORY_SLUG 와 동일
}

/* ===== 공통 헬퍼 ===== */
if (!function_exists('wd_term_id')) {
    function wd_term_id() {
        static $id = null;
        if ($id === null) {
            $t = get_category_by_slug(WD_CATEGORY_SLUG);
            $id = $t ? (int) $t->term_id : 0;
        }
        return $id;
    }
}
if (!function_exists('wd_is_target')) {
    function wd_is_target() {
        $id = wd_term_id();
        if (!$id) { return false; }
        if (is_category($id)) { return true; }
        if (is_singular('post') && in_category($id, get_queried_object_id())) { return true; }
        return false;
    }
}

/* ===== (1) 노출 차단 ===== */
add_filter('wp_robots', function ($robots) {
    if (wd_is_target()) {
        $robots['noindex'] = true; $robots['nofollow'] = true; $robots['noarchive'] = true;
        unset($robots['index'], $robots['follow']);
    }
    return $robots;
});
add_filter('wp_sitemaps_posts_query_args', function ($args, $post_type) {
    if ($post_type === 'post' && wd_term_id()) {
        $args['category__not_in'] = array_merge((array) ($args['category__not_in'] ?? []), [wd_term_id()]);
    }
    return $args;
}, 10, 2);
add_filter('wp_sitemaps_taxonomies_query_args', function ($args, $taxonomy) {
    if ($taxonomy === 'category' && wd_term_id()) {
        $args['exclude'] = array_merge((array) ($args['exclude'] ?? []), [wd_term_id()]);
    }
    return $args;
}, 10, 2);
add_action('pre_get_posts', function ($q) {
    if (is_admin() || !$q->is_main_query()) { return; }
    $id = wd_term_id();
    if (!$id) { return; }
    if ($q->is_home() || $q->is_feed() || $q->is_search()) {
        $not = (array) $q->get('category__not_in'); $not[] = $id;
        $q->set('category__not_in', $not);
    }
});
add_filter('the_posts', function ($posts, $q) {
    if (!is_admin() && $q->is_feed() && wd_term_id()) {
        $id = wd_term_id();
        $posts = array_values(array_filter($posts, function ($p) use ($id) { return !in_category($id, $p); }));
    }
    return $posts;
}, 10, 2);

/* ===== (2) 독립 렌더링 (테마 우회) ===== */
add_action('template_redirect', function () {
    if (!wd_is_target()) { return; }
    if (is_category(wd_term_id())) { wd_render_list(); } else { wd_render_single(); }
    exit;
});

if (!function_exists('wd_clean_title')) {
    function wd_clean_title($t) { return trim(trim((string) $t), '[]'); }
}
if (!function_exists('wd_palette')) {
    function wd_palette($id) {
        $p = [['#6b8cff','#3b53d8'],['#ff9e6b','#ef5f53'],['#3fc9a6','#2a9d8f'],
              ['#a78bfa','#6c5ce7'],['#ff8fb0','#e84a7f'],['#5fb6e5','#2d7fc7']];
        return $p[$id % count($p)];
    }
}
if (!function_exists('wd_week_label')) {
    function wd_week_label($post) {
        $t = get_the_title($post);
        if (preg_match('/(\d{4})\D+?(\d{1,2})\D+?(\d{1,2})\s*주/u', $t, $m)) {
            return $m[1].'년 '.intval($m[2]).'월 '.intval($m[3]).'주';
        }
        if (preg_match('/wd-(\d{4})-(\d{2})-w(\d)/', $post->post_name, $m)) {
            return $m[1].'년 '.intval($m[2]).'월 '.intval($m[3]).'주';
        }
        return get_the_date('Y년 n월', $post);
    }
}
if (!function_exists('wd_theme')) {
    /* 제목(가중치 3)+요약·본문 앞부분에서 키워드를 세어 그 호의 대표 주제 테마를 판별. */
    function wd_theme($post) {
        static $cache = [];
        $pid = (int) $post->ID;
        if (isset($cache[$pid])) { return $cache[$pid]; }
        $themes = [
            ['label'=>'정책','icon'=>'🏛','c'=>['#5b7cfa','#3b53d8'],
             'kw'=>['수가','보험','복지부','제도','정책','급여','개정','국회','예산','지침','고시','법안','규제']],
            ['label'=>'기술','icon'=>'🤖','c'=>['#a78bfa','#6c5ce7'],
             'kw'=>['AI','인공지능','로봇','디지털','스마트','플랫폼','데이터','시스템','자동화','앱','기술']],
            ['label'=>'현장','icon'=>'🩺','c'=>['#3fc9a6','#2a9d8f'],
             'kw'=>['요양보호사','인력','처우','근로','종사자','임금','채용','교육','노동','구인','현장']],
            ['label'=>'시장','icon'=>'📈','c'=>['#ffb15c','#ef8a2b'],
             'kw'=>['실버타운','투자','기업','시장','매출','산업','진출','레지던스','분양','수요','공급','사업']],
            ['label'=>'돌봄','icon'=>'🫶','c'=>['#4ec5e0','#2d7fc7'],
             'kw'=>['치매','돌봄','건강','재가','케어','질환','환자','안심','정서','요양']],
        ];
        $title = (string) get_the_title($post);
        $body  = wp_strip_all_tags(preg_replace('#<style[^>]*>.*?</style>#is', '', (string) $post->post_content));
        $tail  = (string) get_the_excerpt($post).' '.mb_substr($body, 0, 400);
        $best = null; $bestScore = 0;
        foreach ($themes as $t) {
            $s = 0;
            foreach ($t['kw'] as $k) {
                $s += 3 * substr_count($title, $k);
                $s += 1 * substr_count($tail, $k);
            }
            if ($s > $bestScore) { $bestScore = $s; $best = $t; }
        }
        if (!$best) { $best = ['label'=>'주간 브리핑','icon'=>'📰','c'=>['#94a3b8','#64748b']]; }
        return $cache[$pid] = $best;
    }
}
if (!function_exists('wd_cover_html')) {
    function wd_cover_html($post, $size = 'card') {
        $th = wd_theme($post);
        $img = has_post_thumbnail($post)
            ? get_the_post_thumbnail_url($post, $size === 'big' ? 'large' : 'medium_large')
            : '';
        $cls = 'wd-cover wd-cover-'.$size.($img ? ' has-img' : '');  // wd-cover-card | wd-cover-big
        $style = 'background:linear-gradient(135deg,'.$th['c'][0].','.$th['c'][1].');';
        $html = '<div class="'.$cls.'" style="'.$style.'">';
        if ($img) {
            $html .= '<img class="wd-cover-img" loading="lazy" src="'.esc_url($img).'" alt="">';
        }
        $html .= '<span class="wd-cover-chip">'.esc_html($th['label']).'</span>'
               . '<span class="wd-cover-week">'.esc_html(wd_week_label($post)).'</span>'
               . '<span class="wd-cover-brand">SILVERCARE PLUS · WEEKLY</span>'
               . '</div>';
        return $html;
    }
}
if (!function_exists('wd_css')) {
    function wd_css() {
        return <<<CSS
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{background:#fff;color:#1d1d1d;font-family:'Noto Sans KR','Apple SD Gothic Neo',sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
b,strong,h1,h2,h3,h4,h5,h6,.wd-article *{font-weight:400}
.wd-top{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.92);backdrop-filter:saturate(180%) blur(8px);border-bottom:1px solid #ededed}
.wd-top-inner{max-width:1400px;margin:0 auto;height:62px;display:flex;align-items:center;padding:0 24px}
.wd-brand{font-family:'Noto Sans KR','Apple SD Gothic Neo',sans-serif;font-weight:500;font-size:18px;letter-spacing:-.01em;color:#222}
.wd-brand b{font-weight:inherit}
.wd-tagline{margin-left:16px;padding-left:16px;border-left:1px solid #e2e2e2;color:#9a9a9a;font-size:14px;letter-spacing:-.01em}
/* 본문(단일글) 전용 탑바: 태그라인 숨김 + 브랜드 가운데 정렬 */
.wd-top--single .wd-tagline{display:none}
.wd-top--single .wd-top-inner{justify-content:center}
.wd-wrap{max-width:1400px;margin:0 auto;padding:0 24px}
.wd-list{max-width:1400px}
/* 3컬럼 카드 그리드 (naver works Featured 스타일) */
.wd-feed{display:grid;grid-template-columns:repeat(3,1fr);gap:36px 26px;padding:40px 0 90px}
.wd-card{display:flex;flex-direction:column;background:#fff;border:1px solid #ededed;border-radius:12px;overflow:hidden;transition:transform .18s ease,box-shadow .18s ease}
.wd-card:hover{transform:translateY(-4px);box-shadow:0 14px 30px rgba(0,0,0,.10)}
.wd-card:hover .wd-card-title{text-decoration:underline;text-underline-offset:3px}
.wd-card-thumb{width:100%}
.wd-card-body{display:flex;flex-direction:column;flex:1;padding:18px 18px 16px}
.wd-card-title{font-weight:400;font-size:18px;line-height:1.42;margin:0 0 9px;color:#1a1a1a;letter-spacing:-.01em;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
.wd-card-sum{color:#8c8c8c;font-size:14px;line-height:1.62;margin:0 0 16px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.wd-cover{position:relative;overflow:hidden;display:flex;flex-direction:column;color:#fff}
.wd-cover-card{aspect-ratio:3/2;padding:15px 18px}
.wd-cover-img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0}
.wd-cover.has-img::after{content:"";position:absolute;inset:0;z-index:1;background:linear-gradient(180deg,rgba(0,0,0,.30) 0%,rgba(0,0,0,0) 36%,rgba(0,0,0,.58) 100%)}
.wd-cover-chip{position:relative;z-index:2;align-self:flex-start;background:rgba(255,255,255,.22);font-size:12px;font-weight:400;padding:5px 11px;border-radius:999px;letter-spacing:.01em;line-height:1}
.wd-cover.has-img .wd-cover-chip{background:rgba(0,0,0,.42)}
.wd-cover-week{position:relative;z-index:2;margin-top:auto;font-weight:400;font-size:20px;letter-spacing:-.01em;text-shadow:0 1px 6px rgba(0,0,0,.35)}
.wd-cover-brand{position:relative;z-index:2;font-size:10px;letter-spacing:.16em;opacity:.82;font-weight:500;margin-top:5px;text-shadow:0 1px 4px rgba(0,0,0,.35)}
.wd-empty{padding:90px 0;text-align:center;color:#aaa}
.wd-single{max-width:900px}
.wd-hero{padding:48px 0 0}
.wd-cover-big{aspect-ratio:21/9;border-radius:8px;margin-bottom:32px;padding:22px 26px}
.wd-cover-big .wd-cover-chip{font-size:13px;padding:6px 13px}
.wd-cover-big .wd-cover-week{font-size:34px}
.wd-cover-big .wd-cover-brand{font-size:11px}
.wd-hero-title{font-family:'Noto Sans KR','Apple SD Gothic Neo',sans-serif;font-weight:400;font-size:26px;line-height:1.42;margin:0 0 16px;letter-spacing:-.02em}
.wd-hero-meta{color:#9a9a9a;font-size:14px;margin:0;padding-bottom:30px;border-bottom:1px solid #eee}
.wd-article{padding:38px 0 24px}
/* 기발행 글에 박힌 .cwd 본문 스타일 오버라이드 (폭 900px + 시인성 개선) */
.wd-article .cwd{max-width:900px;line-height:1.9}
/* 섹션 제목: 파란 밑줄 → 검정 사각 박스 */
.wd-article .cwd .cwd-ax h2{padding:2px 14px;border:0;background:#1a1a1a;color:#fff;font-weight:500;font-size:16px}
.wd-article .cwd .cwd-ax.muted h2{background:#d6d6d6;color:#fff}
/* 본문 단락: 또렷하게 (weight 400, 17px, 넉넉한 행간·간격) */
.wd-article .cwd .cwd-brief{font-size:17px;font-weight:400;line-height:1.9;margin-bottom:24px;color:#222}
.wd-article .cwd .cwd-ax.muted .cwd-brief{color:#8a8a8a}
/* 메타 회색 진하게 (명도차 축소) */
.wd-article .cwd .cwd-kicker,.wd-article .cwd .cwd-period{color:#666}
.wd-article .cwd .cwd-src{color:#555}
.wd-article .cwd .cwd-src b{color:#444;margin-bottom:8px}
/* 관련기사 썸네일 행 (기발행 글 백필용 — embedded style엔 없음) */
.wd-article .cwd .cwd-rel{display:flex;align-items:center;gap:11px;margin:7px 0;text-decoration:none}
.wd-article .cwd .cwd-rel-th{flex:0 0 auto;width:58px;height:43px;border-radius:6px;object-fit:cover;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:500;overflow:hidden}
.wd-article .cwd .cwd-rel-t{font-size:14px;line-height:1.45;color:#333}
.wd-article .cwd .cwd-rel:hover .cwd-rel-t{text-decoration:underline}
/* 하단 추천 뉴스 섹션 */
.wd-article .cwd .cwd-reco{margin:50px 0 0;padding-top:26px;border-top:2px solid #1a1a1a}
.wd-article .cwd .cwd-reco-h{font-size:18px;font-weight:500;letter-spacing:-.01em;margin:0 0 18px;color:#1a1a1a}
.wd-article .cwd .cwd-reco-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px 16px}
.wd-article .cwd .cwd-reco .cwd-rel{flex-direction:column;align-items:stretch;gap:0;margin:0}
.wd-article .cwd .cwd-reco .cwd-rel-th{width:100%;height:auto;aspect-ratio:4/3;border-radius:8px;margin-bottom:9px;font-size:13px}
.wd-article .cwd .cwd-reco .cwd-rel-t{font-size:13.5px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.wd-article .cwd .cwd-reco .cwd-rel-src{display:block;font-size:12px;color:#9a9a9a;margin-top:5px}
@media(max-width:680px){.wd-article .cwd .cwd-reco-grid{grid-template-columns:repeat(2,1fr)}}
.wd-back{padding:26px 0 90px;border-top:1px solid #eee;margin-top:20px}
.wd-back a{color:#2d7fc7;font-size:15px}
.wd-foot{border-top:1px solid #f0f0f0;background:#fafafa}
.wd-foot p{color:#aaa;font-size:13px;padding:28px 24px;margin:0;text-align:center}
@media(max-width:920px){.wd-feed{grid-template-columns:repeat(2,1fr);gap:30px 22px}}
@media(max-width:600px){.wd-tagline{display:none}.wd-hero-title{font-size:24px}.wd-feed{grid-template-columns:1fr;gap:24px;padding:26px 0 70px}.wd-card-title{font-size:17px}}
CSS;
    }
}
if (!function_exists('wd_doc_head')) {
    function wd_doc_head($title, $desc = '') {
        status_header(200);
        nocache_headers();
        if (!headers_sent()) { header('Content-Type: text/html; charset=UTF-8'); }
        echo '<!doctype html><html lang="ko"><head><meta charset="utf-8">';
        echo '<meta name="viewport" content="width=device-width, initial-scale=1">';
        echo '<meta name="robots" content="noindex,nofollow,noarchive">';
        echo '<title>'.esc_html($title).'</title>';
        if ($desc) { echo '<meta name="description" content="'.esc_attr($desc).'">'; }
        echo '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>';
        echo '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">';
        echo '<style>'.wd_css().'</style></head><body>';
    }
}
if (!function_exists('wd_header_bar')) {
    function wd_header_bar($variant = '') {
        $home = get_category_link(wd_term_id());
        $cls = 'wd-top'.($variant ? ' wd-top--'.$variant : '');
        echo '<header class="'.$cls.'"><div class="wd-top-inner">';
        echo '<a class="wd-brand" href="'.esc_url($home).'"><b>SILVERCARE PLUS</b> · WEEKLY · DIGEST</a>';
        echo '<span class="wd-tagline">매주 발행되는 요양·실버 산업 브리핑</span>';
        echo '</div></header>';
    }
}
if (!function_exists('wd_footer')) {
    function wd_footer() {
        echo '<footer class="wd-foot"><p>발행 : 실버케어플러스 기획팀 · 사내 한정 공유</p></footer>';
        echo '</body></html>';
    }
}
if (!function_exists('wd_render_list')) {
    function wd_render_list() {
        wd_doc_head('실버케어플러스 주간 다이제스트', '요양·실버 산업 주간 동향 브리핑');
        wd_header_bar();
        echo '<main class="wd-wrap wd-list">';
        $q = new WP_Query([
            'cat' => wd_term_id(), 'posts_per_page' => 60,
            'post_status' => 'publish', 'ignore_sticky_posts' => true,
        ]);
        if ($q->have_posts()) {
            echo '<div class="wd-feed">';
            while ($q->have_posts()) {
                $q->the_post();
                $p = get_post();
                $sub = get_the_excerpt();
                $title = $sub ? $sub : wd_clean_title(get_the_title());
                $body = preg_replace('#<style[^>]*>.*?</style>#is', '', $p->post_content);
                $summary = mb_substr(trim(wp_strip_all_tags($body)), 0, 170);
                echo '<a class="wd-card" href="'.esc_url(get_permalink()).'">';
                echo '<div class="wd-card-thumb">'.wd_cover_html($p, 'card').'</div>';
                echo '<div class="wd-card-body">';
                echo '<h2 class="wd-card-title">'.esc_html($title).'</h2>';
                echo '<p class="wd-card-sum">'.esc_html($summary).'</p>';
                echo '</div>';
                echo '</a>';
            }
            echo '</div>';
            wp_reset_postdata();
        } else {
            echo '<p class="wd-empty">아직 발행된 다이제스트가 없습니다.</p>';
        }
        echo '</main>';
        wd_footer();
    }
}
if (!function_exists('wd_render_single')) {
    function wd_render_single() {
        $post = get_queried_object();
        $sub = get_the_excerpt($post);
        $clean = wd_clean_title(get_the_title($post));
        wd_doc_head(get_the_title($post), $sub);
        wd_header_bar('single');
        echo '<main class="wd-wrap wd-single">';
        echo '<header class="wd-hero">';
        echo wd_cover_html($post, 'big');
        echo '<h1 class="wd-hero-title">'.esc_html($sub ? $sub : $clean).'</h1>';
        echo '<p class="wd-hero-meta">'.esc_html(get_the_date('Y년 n월 j일', $post)).' · 실버케어플러스 기획팀</p>';
        echo '</header>';
        echo '<article class="wd-article">'.$post->post_content.'</article>';
        echo '<div class="wd-back"><a href="'.esc_url(get_category_link(wd_term_id())).'">← 다른 호 보기</a></div>';
        echo '</main>';
        wd_footer();
    }
}
