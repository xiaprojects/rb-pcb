/* A* search for generate.py: one 45-degree track on a two-layer grid.
 *
 * State: (layer, x, y, incoming direction). Direction 8 means "no direction yet" (a source or a via).
 * free0/free1/fv are nx*ny byte maps indexed [x*ny+y]; goal is 2*nx*ny bytes indexed [l*nx*ny + x*ny+y].
 * Returns the path length in cells, written to out as l,x,y triples from source to goal,
 * -1 when no path exists, -2 when the expansion limit was reached.
 */
#include <stdint.h>
#include <stdlib.h>
#include <math.h>

typedef struct { float f, g; int k; } Node;

static Node *heap;
static long heap_n, heap_cap;

static void push(Node n)
{
    if (heap_n >= heap_cap) {
        heap_cap = heap_cap ? heap_cap * 2 : 1 << 20;
        heap = realloc(heap, heap_cap * sizeof(Node));
    }
    long i = heap_n++;
    while (i > 0) {
        long p = (i - 1) / 2;
        if (heap[p].f <= n.f)
            break;
        heap[i] = heap[p];
        i = p;
    }
    heap[i] = n;
}

static Node pop(void)
{
    Node top = heap[0], last = heap[--heap_n];
    long i = 0;
    for (;;) {
        long l = 2 * i + 1, r = l + 1, m;
        if (l >= heap_n)
            break;
        m = (r < heap_n && heap[r].f < heap[l].f) ? r : l;
        if (heap[m].f >= last.f)
            break;
        heap[i] = heap[m];
        i = m;
    }
    heap[i] = last;
    return top;
}

static const int DX[8] = {1, 1, 0, -1, -1, -1, 0, 1};
static const int DY[8] = {0, 1, 1, 1, 0, -1, -1, -1};
static const float TURN[3] = {0.0f, 0.8f, 5.0f};

static float heuristic(int x, int y, int tx, int ty)
{
    if (tx < 0)
        return 0.0f;
    int dx = abs(x - tx), dy = abs(y - ty);
    int lo = dx < dy ? dx : dy, hi = dx < dy ? dy : dx;
    return 1.08f * (hi + 0.41421356f * lo);
}

int astar(const uint8_t *free0, const uint8_t *free1, const uint8_t *fv, int nx, int ny,
          const int *src, int nsrc, const uint8_t *goal, int tx, int ty,
          int allow_via, float via_cost, long limit, int *out, int maxlen)
{
    static float *best;
    static int *parent;
    static long capacity;
    long cells = (long)nx * ny, states = cells * 18;
    if (states > capacity) {
        free(best);
        free(parent);
        best = malloc(states * sizeof(float));
        parent = malloc(states * sizeof(int));
        capacity = states;
    }
    for (long i = 0; i < states; i++)
        best[i] = 1e18f;
    heap_n = 0;
#define KEY(l, x, y, d) ((((long)(x) * ny + (y)) * 2 + (l)) * 9 + (d))
    for (int i = 0; i < nsrc; i++) {
        int l = src[3 * i], x = src[3 * i + 1], y = src[3 * i + 2];
        long k = KEY(l, x, y, 8);
        best[k] = 0;
        parent[k] = -1;
        push((Node){heuristic(x, y, tx, ty), 0, (int)k});
    }
    long expanded = 0;
    while (heap_n) {
        Node n = pop();
        long k = n.k;
        if (n.g > best[k])
            continue;
        int d = k % 9;
        long c = k / 9;
        int l = c % 2;
        c /= 2;
        int x = c / ny, y = c % ny;
        if (goal[(long)l * cells + c]) {
            int len = 0;
            for (long p = k; p >= 0; p = parent[p])
                len++;
            if (len > maxlen)
                return -2;
            int i = len;
            for (long p = k; p >= 0; p = parent[p]) {
                long q = p / 9;
                i--;
                out[3 * i] = q % 2;
                q /= 2;
                out[3 * i + 1] = q / ny;
                out[3 * i + 2] = q % ny;
            }
            return len;
        }
        if (limit && ++expanded > limit)
            return -2;
        const uint8_t *fr = l ? free1 : free0;
        for (int nd = 0; nd < 8; nd++) {
            float pen = 0;
            if (d != 8) {
                int turn = abs(nd - d);
                turn = turn < 8 - turn ? turn : 8 - turn;
                if (turn > 2)
                    continue;
                pen = TURN[turn];
            }
            int qx = x + DX[nd], qy = y + DY[nd];
            if (qx < 0 || qy < 0 || qx >= nx || qy >= ny || !fr[(long)qx * ny + qy])
                continue;
            float step = (nd & 1) ? 1.485f : 1.0f;
            if (!(nd & 1) && ((nd % 4 == 0) == (l == 0)))  /* F.Cu prefers y, B.Cu prefers x */
                step *= 1.12f;
            float g = n.g + step + pen;
            long nk = KEY(l, qx, qy, nd);
            if (g < best[nk]) {
                best[nk] = g;
                parent[nk] = (int)k;
                push((Node){g + heuristic(qx, qy, tx, ty), g, (int)nk});
            }
        }
        if (allow_via && fv[c]) {
            float g = n.g + via_cost;
            long nk = KEY(1 - l, x, y, 8);
            if (g < best[nk]) {
                best[nk] = g;
                parent[nk] = (int)k;
                push((Node){g + heuristic(x, y, tx, ty), g, (int)nk});
            }
        }
    }
    return -1;
}
