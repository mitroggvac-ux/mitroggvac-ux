<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 $W $H" width="$W" height="$H" role="img"
     aria-label="ZAMMER — акция 37%" preserveAspectRatio="xMidYMid meet">
  <title>ZAMMER — акция 37%</title>

  <defs>
    <linearGradient id="zm-bg" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="$BG0"/>
      <stop offset=".5" stop-color="$BG1"/>
      <stop offset="1" stop-color="$BG2"/>
    </linearGradient>

    <!-- хромированная лицевая грань: резкая «линия горизонта» на 50 % -->
    <linearGradient id="zm-metal" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="$METAL0"/>
      <stop offset=".30" stop-color="$METAL1"/>
      <stop offset=".495" stop-color="$METAL3"/>
      <stop offset=".505" stop-color="$METAL2"/>
      <stop offset=".80" stop-color="$METAL1"/>
      <stop offset="1" stop-color="$METAL0"/>
    </linearGradient>

    <linearGradient id="zm-hot" x1="0" y1="0" x2=".85" y2="1">
      <stop offset="0" stop-color="$HOT0"/>
      <stop offset=".5" stop-color="$HOT1"/>
      <stop offset="1" stop-color="$HOT2"/>
    </linearGradient>

    <linearGradient id="zm-trail" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="$TRAIL" stop-opacity="0"/>
      <stop offset=".18" stop-color="$TRAIL" stop-opacity=".75"/>
      <stop offset=".5" stop-color="$HOT0" stop-opacity="1"/>
      <stop offset=".82" stop-color="$TRAIL" stop-opacity=".75"/>
      <stop offset="1" stop-color="$TRAIL" stop-opacity="0"/>
    </linearGradient>

    <linearGradient id="zm-wave-g" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="$WAVE" stop-opacity="0"/>
      <stop offset=".42" stop-color="$WAVE" stop-opacity=".22"/>
      <stop offset=".5" stop-color="$WAVE" stop-opacity=".9"/>
      <stop offset=".58" stop-color="$WAVE" stop-opacity=".22"/>
      <stop offset="1" stop-color="$WAVE" stop-opacity="0"/>
    </linearGradient>

    <linearGradient id="zm-wave-soft" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="$WAVE" stop-opacity="0"/>
      <stop offset=".5" stop-color="$WAVE" stop-opacity=".38"/>
      <stop offset="1" stop-color="$WAVE" stop-opacity="0"/>
    </linearGradient>

    <radialGradient id="zm-halo-g" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="$HALO" stop-opacity="1"/>
      <stop offset=".38" stop-color="$HALO" stop-opacity=".55"/>
      <stop offset=".72" stop-color="$HALO" stop-opacity=".16"/>
      <stop offset="1" stop-color="$HALO" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="zm-plate-halo" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="$HOT0" stop-opacity=".9"/>
      <stop offset=".5" stop-color="$HOT1" stop-opacity=".45"/>
      <stop offset="1" stop-color="$HOT2" stop-opacity="0"/>
    </radialGradient>

    <filter id="zm-b-l" x="-60%" y="-300%" width="220%" height="700%">
      <feGaussianBlur stdDeviation="15"/>
    </filter>
    <filter id="zm-b-m" x="-60%" y="-300%" width="220%" height="700%">
      <feGaussianBlur stdDeviation="6"/>
    </filter>
    <filter id="zm-b-s" x="-60%" y="-300%" width="220%" height="700%">
      <feGaussianBlur stdDeviation="2.6"/>
    </filter>
    <filter id="zm-drop" x="-40%" y="-160%" width="200%" height="440%">
      <feDropShadow dx="6" dy="7" stdDeviation="6" flood-color="#000" flood-opacity=".55"/>
    </filter>

    <path id="zm-logo" fill-rule="evenodd" d="$LOGO_D"/>

    <clipPath id="zm-logo-clip">
      <path fill-rule="evenodd" d="$LOGO_D"/>
    </clipPath>
    <clipPath id="zm-frame">
      <rect x="0" y="0" width="$W" height="$H"/>
    </clipPath>
  </defs>

  <style>
    /* Базовое состояние = финальный «зажжённый» кадр.
       Оно же показывается при prefers-reduced-motion: reduce. */
    .zm-wave      { opacity: 0; }
    .zm-spec      { opacity: 0; }
    .zm-halo      { opacity: .7; }
    .zm-ak        { fill: $AK_ON; stroke: $AK_ON; }
    .zm-ak-glow   { opacity: .55; }
    .zm-plate-on  { opacity: 1; }
    .zm-plate-glow{ opacity: .8; }
    .zm-dig       { fill: $DIG_ON; stroke: $DIG_ON; }
    .zm-trail     { opacity: .9; transform: scaleX(1); }
    .zm-spark     { opacity: 0; }
    .zm-grid      { opacity: 1; }

    .zm-halo, .zm-plate-pop, .zm-trail, .zm-spark, .zm-logo-wrap,
    .zm-ak-wrap, .zm-plate-wrap {
      transform-box: fill-box;
      transform-origin: center;
    }
    .zm-trail { transform-origin: left center; }

    @media (prefers-reduced-motion: no-preference) {

      /* ── появление, проигрывается один раз ─────────────────────────── */
      .zm-logo-wrap  { animation: zm-in-up ${INTRO}s cubic-bezier(.16,.84,.24,1) both; }
      .zm-ak-wrap    { animation: zm-in-left .62s cubic-bezier(.16,.84,.24,1) .40s both; }
      .zm-plate-wrap { animation: zm-in-pop .60s cubic-bezier(.2,.9,.3,1.05) .54s both; }

      /* ── цикл ──────────────────────────────────────────────────────── */
      .zm-wave       { animation: zm-wave-run ${LOOP}s linear ${INTRO}s infinite; }
      .zm-spec       { animation: zm-spec-run ${LOOP}s linear ${INTRO}s infinite; }
      .zm-halo       { animation: zm-halo-run ${LOOP}s ease-in-out ${INTRO}s infinite; }
      .zm-ak         { animation: zm-ak-lit ${LOOP}s ease-in-out ${INTRO}s infinite; }
      .zm-ak-glow    { animation: zm-ak-glow ${LOOP}s ease-in-out ${INTRO}s infinite; }
      .zm-plate-on   { animation: zm-plate-on ${LOOP}s ease-out ${INTRO}s infinite; }
      .zm-plate-glow { animation: zm-plate-glow ${LOOP}s ease-out ${INTRO}s infinite; }
      .zm-dig        { animation: zm-dig ${LOOP}s ease-out ${INTRO}s infinite; }
      .zm-plate-pop  { animation: zm-plate-pop ${LOOP}s cubic-bezier(.2,.9,.3,1) ${INTRO}s infinite; }
      .zm-trail      { animation: zm-trail ${LOOP}s linear ${INTRO}s infinite; }
      .zm-grid       { animation: zm-grid ${LOOP}s ease-in-out ${INTRO}s infinite; }
      $SPARK_CSS
    }

    @keyframes zm-in-up {
      from { opacity: 0; transform: translateY(14px) scale(.955); }
      to   { opacity: 1; transform: none; }
    }
    @keyframes zm-in-left {
      from { opacity: 0; transform: translateX(-18px); }
      to   { opacity: 1; transform: none; }
    }
    @keyframes zm-in-pop {
      from { opacity: 0; transform: scale(.86); }
      to   { opacity: 1; transform: none; }
    }

    /* Световая волна: слева направо через весь баннер */
    @keyframes zm-wave-run {
      0%      { opacity: 0; transform: translateX(${WAVE_X0}px); }
      $P_W0   { opacity: 0; transform: translateX(${WAVE_X0}px); }
      $P_WFI  { opacity: 1; }
      $P_WFO  { opacity: 1; }
      $P_W1   { opacity: 0; transform: translateX(${WAVE_X1}px); }
      100%    { opacity: 0; transform: translateX(${WAVE_X1}px); }
    }

    /* Блик, скользящий по буквам ровно вместе с волной */
    @keyframes zm-spec-run {
      0%      { opacity: 0; transform: translateX(${WAVE_X0}px); }
      $P_W0   { opacity: 0; transform: translateX(${WAVE_X0}px); }
      $P_SPEC0{ opacity: 1; }
      $P_SPEC1{ opacity: 1; }
      $P_W1   { opacity: 0; transform: translateX(${WAVE_X1}px); }
      100%    { opacity: 0; transform: translateX(${WAVE_X1}px); }
    }

    /* Подсветка за логотипом: дежурное «дыхание» + вспышка на проходе волны */
    @keyframes zm-halo-run {
      0%      { opacity: .18; transform: scale(.93); }
      $P_LG0  { opacity: .26; transform: scale(.97); }
      $P_LG1  { opacity: 1;   transform: scale(1.07); }
      $P_LG2  { opacity: .62; transform: scale(1); }
      $P_HOLD { opacity: .78; transform: scale(1.04); }
      $P_DIM  { opacity: .18; transform: scale(.93); }
      100%    { opacity: .18; transform: scale(.93); }
    }

    @keyframes zm-ak-lit {
      0%, $P_AK0 { fill: $AK_OFF; stroke: $AK_OFF; }
      $P_AK1     { fill: $AK_ON;  stroke: $AK_ON; }
      $P_HOLD    { fill: $AK_ON;  stroke: $AK_ON; }
      $P_DIM     { fill: $AK_OFF; stroke: $AK_OFF; }
      100%       { fill: $AK_OFF; stroke: $AK_OFF; }
    }
    @keyframes zm-ak-glow {
      0%, $P_AK0 { opacity: 0; }
      $P_AK1     { opacity: .75; }
      $P_HOLD    { opacity: .45; }
      $P_DIM     { opacity: 0; }
      100%       { opacity: 0; }
    }

    /* Поджиг акции в момент, когда до неё доходит волна */
    @keyframes zm-plate-on {
      0%, $P_PL0 { opacity: 0; }
      $P_PL1     { opacity: 1; }
      $P_HOLD    { opacity: 1; }
      $P_DIM     { opacity: 0; }
      100%       { opacity: 0; }
    }
    @keyframes zm-dig {
      0%, $P_PL0 { fill: $DIG_OFF; stroke: $DIG_OFF; }
      $P_PL1     { fill: $DIG_ON;  stroke: $DIG_ON; }
      $P_HOLD    { fill: $DIG_ON;  stroke: $DIG_ON; }
      $P_DIM     { fill: $DIG_OFF; stroke: $DIG_OFF; }
      100%       { fill: $DIG_OFF; stroke: $DIG_OFF; }
    }
    @keyframes zm-plate-glow {
      0%, $P_PL0 { opacity: 0; }
      $P_PL1     { opacity: 1; }
      $P_PL2     { opacity: .62; }
      $P_HOLD    { opacity: .85; }
      $P_DIM     { opacity: 0; }
      100%       { opacity: 0; }
    }
    @keyframes zm-plate-pop {
      0%, $P_PL0 { transform: scale(1); }
      $P_PL1     { transform: scale(1.11); }
      $P_PL2     { transform: scale(1); }
      100%       { transform: scale(1); }
    }

    /* След волны по нижней кромке баннера */
    @keyframes zm-trail {
      0%, $P_TR0 { opacity: 0; transform: scaleX(0); }
      $P_TR1     { opacity: 1; transform: scaleX(1); }
      $P_HOLD    { opacity: .9; transform: scaleX(1); }
      $P_DIM     { opacity: 0; transform: scaleX(1); }
      100%       { opacity: 0; transform: scaleX(0); }
    }

    @keyframes zm-grid {
      0%, $P_TR0 { opacity: .5; }
      $P_TR1     { opacity: 1; }
      $P_HOLD    { opacity: .9; }
      $P_DIM     { opacity: .5; }
      100%       { opacity: .5; }
    }
    $SPARK_KF
  </style>

  <g clip-path="url(#zm-frame)">
    <rect width="$W" height="$H" fill="url(#zm-bg)"/>
    <g class="zm-grid" stroke="$GRID" stroke-opacity="$GRID_OP" stroke-width="2" fill="none">$GRID_PATHS</g>

    <!-- активная подсветка за логотипом -->
    <g class="zm-halo">
      <ellipse cx="$HALO_CX" cy="45" rx="315" ry="56" fill="url(#zm-halo-g)" filter="url(#zm-b-l)"/>
      <ellipse cx="$HALO_CX" cy="45" rx="225" ry="30" fill="url(#zm-halo-g)" filter="url(#zm-b-m)"/>
      <ellipse cx="$HALO_CX" cy="45" rx="$LOGO_HALF" ry="9" fill="url(#zm-halo-g)"
               filter="url(#zm-b-m)" opacity=".9"/>
    </g>

    <!-- логотип: 3D-выдавливание + металлическая лицевая грань + блик -->
    <g class="zm-logo-wrap">
      <g filter="url(#zm-drop)">
      $EXT
      </g>
      <use href="#zm-logo" xlink:href="#zm-logo" x="-1" y="-1" fill="$RIM" fill-opacity="$RIM_OP"/>
      <use href="#zm-logo" xlink:href="#zm-logo" fill="url(#zm-metal)"/>
      <g clip-path="url(#zm-logo-clip)">
        <g class="zm-spec">
          <g transform="skewX(-12)">
            <rect x="-78" y="-40" width="156" height="180" fill="url(#zm-wave-g)"/>
          </g>
        </g>
      </g>
    </g>

    <!-- АКЦИЯ -->
    <g class="zm-ak-wrap">
      <path class="zm-ak-glow" d="$AK_D" fill="$AK_GLOW" stroke="$AK_GLOW"
            stroke-width="$AK_STROKE" stroke-linejoin="round" filter="url(#zm-b-m)"/>
      <path class="zm-ak" d="$AK_D" stroke-width="$AK_STROKE"
            stroke-linejoin="round" paint-order="stroke fill"/>
    </g>

    <!-- 37% -->
    <g class="zm-plate-wrap">
      <rect class="zm-plate-glow" x="$PLATE_X" y="$PLATE_Y" width="$PLATE_W" height="$PLATE_H"
            rx="$PLATE_R" fill="url(#zm-plate-halo)" filter="url(#zm-b-l)"/>
      <g class="zm-plate-pop">
        <rect x="$PLATE_X" y="$PLATE_Y" width="$PLATE_W" height="$PLATE_H" rx="$PLATE_R"
              fill="$PLATE_OFF" stroke="$PLATE_STROKE_OFF" stroke-width="1.6"/>
        <rect class="zm-plate-on" x="$PLATE_X" y="$PLATE_Y" width="$PLATE_W" height="$PLATE_H"
              rx="$PLATE_R" fill="url(#zm-hot)" stroke="$HOT_STROKE" stroke-width="1.6"/>
        <path class="zm-dig" d="$PC_D" stroke-width="$PC_STROKE" stroke-linejoin="round"
              paint-order="stroke fill"/>
      </g>
      <g fill="$HOT0">
      $SPARKS
      </g>
    </g>

    <!-- след световой волны по нижней кромке -->
    <rect class="zm-trail" x="0" y="86.5" width="$W" height="3.5" fill="url(#zm-trail)"/>

    <!-- сама световая волна -->
    <g class="zm-wave">
      <g transform="skewX(-12)">
        <rect x="-330" y="-60" width="660" height="220" fill="url(#zm-wave-soft)"
              opacity=".7" filter="url(#zm-b-l)"/>
        <rect x="-150" y="-60" width="300" height="220" fill="url(#zm-wave-g)"
              opacity=".85" filter="url(#zm-b-m)"/>
        <rect x="-4" y="-60" width="8" height="220" fill="$WAVE" opacity=".95"
              filter="url(#zm-b-s)"/>
      </g>
    </g>
  </g>
</svg>
