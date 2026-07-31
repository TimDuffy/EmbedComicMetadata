zip:
	rm -f 'EmbedComicMetadata.zip'
	zip -r 'EmbedComicMetadata.zip' * -x ".git/*" ".devcontainer/*" "test-config/*" "test-library/*"
