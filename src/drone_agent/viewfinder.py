"""Pixel-coordinate viewfinder shared by model observations and the dashboard."""
import cv2
import numpy as np


def render_viewfinder(pixels, frame):
    result=pixels.copy()
    rectangle=frame['rectangle']
    if rectangle is None:return result
    x,y,w,h=(rectangle[k] for k in ('left','top','width','height'))
    region=result[y:y+h,x:x+w]
    border=np.zeros((h,w),dtype=np.uint8)
    grid=np.zeros_like(border)

    def dashed(start, end, dash=16, gap=12):
        a,b=np.asarray(start,dtype=float),np.asarray(end,dtype=float)
        length=float(np.linalg.norm(b-a))
        if length==0:return
        direction=(b-a)/length
        for distance in range(0,int(length)+1,dash+gap):
            p=tuple(np.rint(a+direction*distance).astype(int))
            q=tuple(np.rint(a+direction*min(distance+dash,length)).astype(int))
            cv2.line(border,p,q,255,1,cv2.LINE_AA)

    fractions={'none':(), 'thirds':(1/3,2/3), 'golden':(.38196601125,.61803398875)}[frame.get('guides','none')]
    for fraction in fractions:
        gx,gy=round((w-1)*fraction),round((h-1)*fraction)
        cv2.line(grid,(gx,0),(gx,h-1),255,1,cv2.LINE_AA)
        cv2.line(grid,(0,gy),(w-1,gy),255,1,cv2.LINE_AA)
    height,width=pixels.shape[:2]
    if x>0:dashed((0,0),(0,h-1))
    if x+w<width:dashed((w-1,0),(w-1,h-1))
    if y>0:dashed((0,0),(w-1,0))
    if y+h<height:dashed((0,h-1),(w-1,h-1))
    alpha=np.maximum(border.astype(np.float32)*(.65/255),grid.astype(np.float32)*(.28/255))
    if not np.any(alpha):return result
    frost=cv2.GaussianBlur(alpha,(5,5),.85)[:,:,None]*.18
    base=region.astype(np.float32)
    softened=cv2.GaussianBlur(base,(5,5),1.1)
    glass=base*(1-frost)+softened*frost
    alpha=alpha[:,:,None]
    region[:]=np.rint(glass*(1-alpha)+250.*alpha).clip(0,255).astype(np.uint8)
    return result
