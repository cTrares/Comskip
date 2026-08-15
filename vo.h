#ifndef _VO_H
#define _VO_H
void vo_init(int width, int height, char *title);
void vo_draw(unsigned char * buf);
void vo_refresh();
void vo_wait();
void vo_close();
void ShowHelp(char **ta);
void ShowDetails(char *t);
#define REVIEW_SAVE_CONFIRM_CANCEL 0
#define REVIEW_SAVE_CONFIRM_YES 1
#define REVIEW_SAVE_CONFIRM_NO 2
int ConfirmReviewSave(void);
#endif
