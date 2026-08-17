#include <assert.h>
#include <stdio.h>

#include "../review_navigation.h"

int main(void)
{
    const double fps = 25.0;
    const int frame_count = 10000;
    const int middle = 5000;

    assert(ReviewNavigateVertical(middle, 40, fps, frame_count) == 5025);
    assert(ReviewNavigateVertical(5025, 38, fps, frame_count) == middle);
    assert(ReviewNavigateVertical(middle, 34, fps, frame_count) == 5500);
    assert(ReviewNavigateVertical(5500, 33, fps, frame_count) == middle);
    assert(ReviewNavigateVertical(1, 38, fps, frame_count) == 1);
    assert(ReviewNavigateVertical(1, 33, fps, frame_count) == 1);
    assert(ReviewNavigateVertical(frame_count - 1, 40, fps, frame_count) == frame_count - 1);
    assert(ReviewNavigateVertical(frame_count - 1, 34, fps, frame_count) == frame_count - 1);

    puts("review navigation directions and bounds: OK");
    return 0;
}
