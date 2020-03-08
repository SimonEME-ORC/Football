from io import BytesIO
from PIL import Image
from typing import List


def stitch(images: List[Image.Image]) -> BytesIO:
	""" Stich images side by side """
	# images is a list of opened PIL images.
	w = int(images[0].width / 3 * 2 + sum(i.width / 3 for i in images))
	h = images[0].height
	canvas = Image.new('RGB', (w, h))
	x = 0
	for i in images:
		canvas.paste(i, (x, 0))
		x += int(i.width / 3)
	output = BytesIO()
	canvas.save(output, 'PNG')
	
	output.seek(0)
	return output
