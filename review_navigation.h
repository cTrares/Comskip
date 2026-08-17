#ifndef COMSKIP_REVIEW_NAVIGATION_H
#define COMSKIP_REVIEW_NAVIGATION_H

static inline int ReviewNavigateVertical(int current_frame, int key_code, double frames_per_second,
                                         int frame_count)
{
    if (key_code == 40) current_frame += (int)frames_per_second;
    if (key_code == 38) current_frame -= (int)frames_per_second;
    if (key_code == 34) current_frame += (int)(20 * frames_per_second);
    if (key_code == 33) current_frame -= (int)(20 * frames_per_second);

    if (current_frame < 1) current_frame = 1;
    if (frame_count > 0 && current_frame >= frame_count) current_frame = frame_count - 1;
    return current_frame;
}

#endif
