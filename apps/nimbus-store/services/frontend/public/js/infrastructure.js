const Infrastructure = {
  async load() {
    try {
      const response = await fetch('/api/correlation', {
        cache: 'no-store'
      });

      const data = await response.json();

      // fetch() does not reject for HTTP 404/500.
      // Always inspect the JSON response first.
      if (data.status === 'no_data') {
        renderEmptyState(data.message);
        return;
      }

      if (data.status === 'error') {
        renderError(data.message);
        return;
      }

      if (!response.ok) {
        renderError('Unable to load infrastructure data.');
        return;
      }

      renderDashboard(data);

    } catch (error) {
      console.error(
        '[infrastructure] Failed to load:',
        error
      );

      renderError(
        'Unable to connect to the infrastructure API.'
      );
    }
  }
};


/* =========================================================
   DATA HELPERS
   ========================================================= */

function getAffectedNodes(data) {
  return data.changed_nodes || [];
}


function getCorrelatedServices(data) {
  const affected = getAffectedNodes(data);
  const correlatedSet = new Set();

  Object.values(data.correlations || {}).forEach(
    (correlation) => {

      (correlation.related_services || []).forEach(
        (service) => {

          if (!affected.includes(service)) {
            correlatedSet.add(service);
          }

        }
      );

    }
  );

  return [...correlatedSet];
}


function getGraphNodes(data) {
  return [
    ...new Set([
      ...getAffectedNodes(data),
      ...getCorrelatedServices(data)
    ])
  ];
}


/*
 * Node state is derived entirely from backend data.
 *
 * changed_nodes -> affected
 * related services -> correlated
 * everything else -> unaffected
 */
function getNodeStatus(name, data) {
  const affected = getAffectedNodes(data);
  const correlated = getCorrelatedServices(data);

  if (affected.includes(name)) {
    return 'affected';
  }

  if (correlated.includes(name)) {
    return 'correlated';
  }

  return 'unaffected';
}


function displayName(serviceName) {
  return serviceName
    .replace(/^ii-/, '')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}


/*
 * Extract directed relationships from the correlation graph.
 *
 * IMPORTANT:
 *
 * These are separate:
 *
 * product-service -> postgres :5432
 * order-service   -> postgres :5432
 *
 * They must NOT collide just because they share the
 * same target and port.
 */
function getGraphEdges(data) {
  const edges = [];
  const seen = new Set();

  Object.entries(data.correlations || {}).forEach(
    ([service, correlation]) => {

      (correlation.relationships || []).forEach(
        (relationship) => {

          let source;
          let target;

          if (
            relationship.direction === 'outgoing'
          ) {
            source = service;
            target = relationship.related_service;

          } else if (
            relationship.direction === 'incoming'
          ) {
            source = relationship.related_service;
            target = service;

          } else {
            return;
          }

          const port =
            relationship.remote_port ?? null;

          /*
           * Deduplicate only exact source + target + port
           * combinations.
           */
          const key =
            `${source}|${target}|${port}`;

          if (seen.has(key)) {
            return;
          }

          seen.add(key);

          edges.push({
            source,
            target,
            remote_port: port
          });

        }
      );

    }
  );

  return edges;
}


/*
 * Preserve the timestamp that came from the backend.
 *
 * Do NOT use new Date() here as a fallback because that
 * would represent browser refresh time rather than the
 * time the topology snapshot was captured.
 */
function getObservedTimestamp(data) {
  const candidates = [
    data.generated_at,
    data.observed_at,
    data.timestamp,
    data.event_timestamp,
    data.captured_at
  ];

  for (const value of candidates) {

    if (!value) {
      continue;
    }

    const date = new Date(value);

    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleString();
    }
  }

  return 'Timestamp unavailable';
}


/* =========================================================
   DASHBOARD RENDERING
   ========================================================= */

function renderDashboard(data) {
  const affected =
    getAffectedNodes(data);

  const correlated =
    getCorrelatedServices(data);

  const removedConnections =
    data.removed_edges || [];


  /*
   * These numbers are computed from the actual JSON.
   * Nothing is hardcoded.
   */
  document.getElementById(
    'affected-count'
  ).textContent = affected.length;


  document.getElementById(
    'correlated-count'
  ).textContent = correlated.length;


  document.getElementById(
    'removed-count'
  ).textContent = removedConnections.length;


  renderAffectedServices(
    affected
  );


  renderRemovedConnections(
    removedConnections
  );


  renderGraph(
    data
  );


  /*
   * This is the observation timestamp from the backend,
   * not the browser refresh timestamp.
   */
  document.getElementById(
    'last-updated'
  ).textContent =
    getObservedTimestamp(data);


  showDashboard();
}


/* =========================================================
   AFFECTED SERVICES
   ========================================================= */

function renderAffectedServices(services) {
  const container =
    document.getElementById(
      'affected-services'
    );

  if (!services.length) {

    container.innerHTML =
      '<p class="infra-muted">' +
      'No affected services detected.' +
      '</p>';

    return;
  }

  container.innerHTML = services
    .map(
      (service) => `
        <div class="infra-service affected-service">

          <span class="status-dot affected"></span>

          <span>
            ${escapeHtml(
              displayName(service)
            )}
          </span>

        </div>
      `
    )
    .join('');
}


/* =========================================================
   REMOVED CONNECTIONS
   ========================================================= */

function renderRemovedConnections(edges) {
  const container =
    document.getElementById(
      'removed-connections'
    );

  if (!edges.length) {

    container.innerHTML =
      '<p class="infra-muted">' +
      'No removed connections detected.' +
      '</p>';

    return;
  }

  container.innerHTML = edges
    .map(
      (edge) => `
        <div class="connection-row">

          <span>
            ${escapeHtml(
              displayName(edge.source)
            )}
          </span>

          <span class="connection-arrow">
            →
          </span>

          <span>
            ${escapeHtml(
              displayName(edge.target)
            )}
          </span>

          <span class="connection-port">
            :${escapeHtml(
              String(edge.remote_port ?? '—')
            )}
          </span>

        </div>
      `
    )
    .join('');
}


/* =========================================================
   GRAPH
   ========================================================= */

function renderGraph(data) {
  const svg =
    document.getElementById(
      'dependency-graph'
    );

  const nodes =
    getGraphNodes(data);

  const edges =
    getGraphEdges(data);


  const nodeWidth = 190;
  const nodeHeight = 76;

  const width = 760;
  const height = 430;


  svg.setAttribute(
    'viewBox',
    `0 0 ${width} ${height}`
  );


  svg.innerHTML = '';


  /*
   * Create the arrowhead definition before drawing edges.
   */
  createArrowMarker(svg);


  const positions =
    calculateLayout(
      nodes,
      edges,
      nodeWidth,
      nodeHeight,
      width
    );


  /*
   * Edges are drawn first so that nodes appear above them.
   */
  drawGraphEdges(
    svg,
    edges,
    positions,
    nodeWidth,
    nodeHeight
  );


  drawGraphNodes(
    svg,
    nodes,
    data,
    positions,
    nodeWidth,
    nodeHeight
  );
}


/* =========================================================
   GRAPH LAYOUT
   ========================================================= */

/*
 * Generic layered graph layout.
 *
 * Nodes are placed according to dependency direction:
 *
 * source
 *   |
 *   v
 * target
 *
 * Nodes in the same layer receive horizontal spacing.
 *
 * No service names are used to determine coordinates.
 */
function calculateLayout(
  nodes,
  edges,
  nodeWidth,
  nodeHeight,
  width
) {
  const adjacency = {};
  const indegree = {};


  nodes.forEach(
    (node) => {
      adjacency[node] = [];
      indegree[node] = 0;
    }
  );


  edges.forEach(
    (edge) => {

      if (
        adjacency[edge.source] &&
        adjacency[edge.target]
      ) {

        adjacency[edge.source].push(
          edge.target
        );

        indegree[edge.target]++;
      }

    }
  );


  /*
   * Find root nodes.
   *
   * A root has no incoming dependency edge.
   */
  let roots =
    nodes.filter(
      (node) => indegree[node] === 0
    );


  /*
   * If the graph is cyclic and therefore has no root,
   * start from the first node.
   */
  if (
    !roots.length &&
    nodes.length
  ) {
    roots = [nodes[0]];
  }


  const layers = [];
  const assigned = new Set();

  let currentLayer = roots;


  /*
   * Breadth-first layering.
   */
  while (
    currentLayer.length
  ) {

    const uniqueLayer = [
      ...new Set(currentLayer)
    ].filter(
      (node) =>
        !assigned.has(node)
    );


    if (!uniqueLayer.length) {
      break;
    }


    layers.push(
      uniqueLayer
    );


    uniqueLayer.forEach(
      (node) => {
        assigned.add(node);
      }
    );


    const nextLayer = [];


    uniqueLayer.forEach(
      (node) => {

        (
          adjacency[node] || []
        ).forEach(
          (target) => {

            if (
              !assigned.has(target)
            ) {
              nextLayer.push(target);
            }

          }
        );

      }
    );


    currentLayer =
      nextLayer;
  }


  /*
   * Put disconnected/unreached nodes into fallback layers.
   */
  const remaining =
    nodes.filter(
      (node) =>
        !assigned.has(node)
    );


  remaining.forEach(
    (node) => {
      layers.push([node]);
    }
  );


  const positions = {};


  /*
   * Explicit spacing prevents node boxes from touching.
   */
  const horizontalGap = 90;
  const verticalGap = 100;


  layers.forEach(
    (layer, layerIndex) => {

      const totalWidth =
        layer.length * nodeWidth +
        (layer.length - 1) *
        horizontalGap;


      let startX =
        Math.max(
          30,
          (width - totalWidth) / 2
        );


      const y =
        45 +
        layerIndex *
        (nodeHeight + verticalGap);


      layer.forEach(
        (node) => {

          positions[node] = {
            x: startX,
            y
          };


          startX +=
            nodeWidth +
            horizontalGap;
        }
      );

    }
  );


  return positions;
}


/* =========================================================
   SVG HELPER
   ========================================================= */

/*
 * Creates SVG elements correctly.
 *
 * IMPORTANT:
 * SVG elements must use the SVG namespace.
 */
function createSvgElement(tag) {
  return document.createElementNS(
    'http://www.w3.org/2000/svg',
    tag
  );
}


/* =========================================================
   ARROWHEAD
   ========================================================= */

function createArrowMarker(svg) {

  const defs =
    createSvgElement(
      'defs'
    );


  const marker =
    createSvgElement(
      'marker'
    );


  marker.setAttribute(
    'id',
    'arrowhead'
  );

  marker.setAttribute(
    'markerWidth',
    '10'
  );

  marker.setAttribute(
    'markerHeight',
    '7'
  );

  marker.setAttribute(
    'refX',
    '9'
  );

  marker.setAttribute(
    'refY',
    '3.5'
  );

  marker.setAttribute(
    'orient',
    'auto'
  );


  const polygon =
    createSvgElement(
      'polygon'
    );


  polygon.setAttribute(
    'points',
    '0 0, 10 3.5, 0 7'
  );


  polygon.setAttribute(
    'class',
    'graph-arrow'
  );


  marker.appendChild(
    polygon
  );


  defs.appendChild(
    marker
  );


  svg.appendChild(
    defs
  );
}


/* =========================================================
   GRAPH EDGES
   ========================================================= */

function drawGraphEdges(
  svg,
  edges,
  positions,
  nodeWidth,
  nodeHeight
) {

  edges.forEach(
    (edge) => {

      const source =
        positions[
          edge.source
        ];

      const target =
        positions[
          edge.target
        ];


      if (
        !source ||
        !target
      ) {
        return;
      }


      const sourceCenter = {
        x:
          source.x +
          nodeWidth / 2,

        y:
          source.y +
          nodeHeight / 2
      };


      const targetCenter = {
        x:
          target.x +
          nodeWidth / 2,

        y:
          target.y +
          nodeHeight / 2
      };


      const points =
        calculateEdgePoints(
          sourceCenter,
          targetCenter,
          nodeWidth,
          nodeHeight
        );


      /*
       * Draw the actual dependency line.
       */
      const line =
        createSvgElement(
          'line'
        );


      line.setAttribute(
        'x1',
        points.start.x
      );

      line.setAttribute(
        'y1',
        points.start.y
      );

      line.setAttribute(
        'x2',
        points.end.x
      );

      line.setAttribute(
        'y2',
        points.end.y
      );


      line.setAttribute(
        'class',
        'graph-edge'
      );


      /*
       * Direction: source -> target.
       */
      line.setAttribute(
        'marker-end',
        'url(#arrowhead)'
      );


      svg.appendChild(
        line
      );


      /*
       * Draw the remote port directly on the graph.
       */
      if (
        edge.remote_port !== null
      ) {

        const midpointX =
          (
            points.start.x +
            points.end.x
          ) / 2;


        const midpointY =
          (
            points.start.y +
            points.end.y
          ) / 2;


        const text =
          createSvgElement(
            'text'
          );


        text.setAttribute(
          'x',
          midpointX
        );


        text.setAttribute(
          'y',
          midpointY - 8
        );


        text.setAttribute(
          'text-anchor',
          'middle'
        );


        text.setAttribute(
          'class',
          'graph-edge-label'
        );


        text.textContent =
          `:${edge.remote_port}`;


        svg.appendChild(
          text
        );
      }

    }
  );
}


/* =========================================================
   EDGE / NODE INTERSECTION
   ========================================================= */

/*
 * Find where the line between two node centers intersects
 * the rectangular boundary of the source and target boxes.
 */
function calculateEdgePoints(
  source,
  target,
  nodeWidth,
  nodeHeight
) {

  const dx =
    target.x -
    source.x;


  const dy =
    target.y -
    source.y;


  const absDx =
    Math.abs(dx);


  const absDy =
    Math.abs(dy);


  const halfWidth =
    nodeWidth / 2;


  const halfHeight =
    nodeHeight / 2;


  /*
   * Avoid division by zero for overlapping centers.
   */
  if (
    absDx === 0 &&
    absDy === 0
  ) {

    return {
      start: source,
      end: target
    };
  }


  let scale;


  if (
    absDx / halfWidth >
    absDy / halfHeight
  ) {

    scale =
      halfWidth /
      absDx;

  } else {

    scale =
      halfHeight /
      absDy;
  }


  const start = {
    x:
      source.x +
      dx * scale,

    y:
      source.y +
      dy * scale
  };


  const end = {
    x:
      target.x -
      dx * scale,

    y:
      target.y -
      dy * scale
  };


  return {
    start,
    end
  };
}


/* =========================================================
   GRAPH NODES
   ========================================================= */

function drawGraphNodes(
  svg,
  nodes,
  data,
  positions,
  nodeWidth,
  nodeHeight
) {

  nodes.forEach(
    (node) => {

      const position =
        positions[node];


      const status =
        getNodeStatus(
          node,
          data
        );


      const group =
        createSvgElement(
          'g'
        );


      group.setAttribute(
        'transform',
        `translate(${position.x}, ${position.y})`
      );


      group.setAttribute(
        'class',
        `graph-node ${status}`
      );


      /*
       * Node rectangle.
       */
      const rect =
        createSvgElement(
          'rect'
        );


      rect.setAttribute(
        'width',
        nodeWidth
      );


      rect.setAttribute(
        'height',
        nodeHeight
      );


      rect.setAttribute(
        'rx',
        '12'
      );


      group.appendChild(
        rect
      );


      /*
       * Status dot.
       */
      const dot =
        createSvgElement(
          'circle'
        );


      dot.setAttribute(
        'cx',
        '22'
      );


      dot.setAttribute(
        'cy',
        '38'
      );


      dot.setAttribute(
        'r',
        '7'
      );


      dot.setAttribute(
        'class',
        'graph-status-dot'
      );


      group.appendChild(
        dot
      );


      /*
       * Service name.
       */
      const label =
        createSvgElement(
          'text'
        );


      label.setAttribute(
        'x',
        '40'
      );


      label.setAttribute(
        'y',
        '34'
      );


      label.setAttribute(
        'class',
        'graph-node-label'
      );


      label.textContent =
        displayName(node);


      group.appendChild(
        label
      );


      /*
       * Status text.
       */
      const statusText =
        createSvgElement(
          'text'
        );


      statusText.setAttribute(
        'x',
        '40'
      );


      statusText.setAttribute(
        'y',
        '56'
      );


      statusText.setAttribute(
        'class',
        'graph-node-status'
      );


      statusText.textContent =
        status === 'affected'
          ? 'Affected'
          : status === 'correlated'
            ? 'Correlated'
            : 'Unaffected';


      group.appendChild(
        statusText
      );


      svg.appendChild(
        group
      );
    }
  );
}


/* =========================================================
   UI STATES
   ========================================================= */

function renderEmptyState(message) {

  document.getElementById(
    'loading-state'
  ).style.display = 'none';


  document.getElementById(
    'dashboard-content'
  ).style.display = 'none';


  document.getElementById(
    'error-state'
  ).style.display = 'none';


  const empty =
    document.getElementById(
      'empty-state'
    );


  empty.style.display =
    'block';


  document.getElementById(
    'empty-message'
  ).textContent =
    message ||
    'No infrastructure data is available.';
}


function renderError(message) {

  document.getElementById(
    'loading-state'
  ).style.display = 'none';


  document.getElementById(
    'dashboard-content'
  ).style.display = 'none';


  document.getElementById(
    'empty-state'
  ).style.display = 'none';


  const error =
    document.getElementById(
      'error-state'
    );


  error.style.display =
    'block';


  document.getElementById(
    'error-message'
  ).textContent =
    message ||
    'Failed to load infrastructure data.';
}


function showDashboard() {

  document.getElementById(
    'loading-state'
  ).style.display = 'none';


  document.getElementById(
    'empty-state'
  ).style.display = 'none';


  document.getElementById(
    'error-state'
  ).style.display = 'none';


  document.getElementById(
    'dashboard-content'
  ).style.display = 'block';
}


/* =========================================================
   HTML ESCAPING
   ========================================================= */

function escapeHtml(value) {
  return String(value)
    .replace(
      /&/g,
      '&amp;'
    )
    .replace(
      /</g,
      '&lt;'
    )
    .replace(
      />/g,
      '&gt;'
    )
    .replace(
      /"/g,
      '&quot;'
    )
    .replace(
      /'/g,
      '&#039;'
    );
}


/* =========================================================
   INITIALIZATION
   ========================================================= */

document.addEventListener(
  'DOMContentLoaded',
  () => {

    Infrastructure.load();


    document
      .getElementById(
        'refresh-infrastructure'
      )
      .addEventListener(
        'click',
        () => {
          Infrastructure.load();
        }
      );

  }
);